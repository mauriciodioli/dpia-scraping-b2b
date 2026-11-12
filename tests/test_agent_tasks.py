"""Task routes and real repository transactions in an isolated database."""
import unittest
from datetime import datetime, timedelta
from sqlalchemy import MetaData, Table, Column, String, Integer, Boolean, DateTime, JSON, select, text
import test_agent_configuration as fixture
from routes.agent_task_routes import task_bp
from model.agent_tasks import AgentTaskRepository
from services.agent_tasks import AgentTaskService
from services.agent_configuration import tareas
from utils.db import db


class AgentTaskTests(unittest.TestCase):
    tearDown = fixture.AgentConfigurationTests.tearDown
    login = fixture.AgentConfigurationTests.login
    save = fixture.AgentConfigurationTests.save

    def setUp(self):
        fixture.AgentConfigurationTests.setUp(self)
        self.app.register_blueprint(task_bp)
        self.agent_id = self.save().json['agent']['id']
        self.app.extensions['agent_task_service'] = AgentTaskService(AgentTaskRepository(db.engine))
        metadata = MetaData()
        self.engines = Table('ae_agents', metadata, Column('id', String, primary_key=True),
                             Column('owner_id', Integer), Column('legacy_agent_id', Integer))
        self.schedules = Table('ae_schedules', metadata, Column('id', String, primary_key=True),
            Column('owner_id', Integer), Column('agent_id', String), Column('legacy_task_id', Integer),
            Column('enabled', Boolean), Column('revision', Integer), Column('next_run_at', DateTime),
            Column('definition', JSON), Column('timezone', String))
        metadata.create_all(db.engine)
        with db.engine.begin() as conn:
            self.ids = conn.execute(select(tareas.c.id).order_by(tareas.c.id)).scalars().all()
            conn.execute(self.engines.insert().values(id='engine', owner_id=self.a, legacy_agent_id=self.agent_id))
            for task_id in self.ids:
                conn.execute(self.schedules.insert().values(id=str(task_id), owner_id=self.a, agent_id='engine',
                    legacy_task_id=task_id, enabled=True, revision=1, next_run_at=datetime.now()+timedelta(days=1),
                    definition={'frequency':'DAILY','execution_time':'09:30'}, timezone='Europe/Rome'))
        self.url = f'/api/agentes/{self.agent_id}/tareas'

    def change(self, action, task_id=None):
        url = self.url + '/' + str(task_id or self.ids[0])
        headers = {'X-DPIA-Action':'manage-task'}
        return self.client.delete(url, headers=headers) if action == 'eliminar' else self.client.patch(url+'/'+action, headers=headers)

    def test_independent_persistent_idempotent_states_and_history(self):
        self.assertEqual(self.client.get(self.url).json['count'], 2)
        for _ in range(2):
            response = self.change('pausar')
            self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual([t['state'] for t in response.json['tasks']], ['paused','active'])
        self.assertEqual(self.client.get('/api/agente/configuracion').status_code, 200)
        self.assertEqual(self.change('activar').status_code, 200)
        for _ in range(2):
            response = self.change('eliminar')
            self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.client.get(self.url).json['count'], 1)
        self.assertEqual(self.change('activar').status_code, 404)
        with db.engine.connect() as conn:
            rows = conn.execute(select(tareas).order_by(tareas.c.id)).mappings().all()
            self.assertEqual(len(rows), 2)
            self.assertIn('_deleted_at', rows[0]['parametros'])
            self.assertTrue(rows[1]['habilitada'])
            schedules = conn.execute(select(self.schedules).order_by(self.schedules.c.id)).mappings().all()
            self.assertFalse(schedules[0]['enabled'])
            self.assertTrue(schedules[1]['enabled'])
        self.assertEqual(self.client.get('/api/agente/configuracion').status_code, 200)

    def test_ownership_session_and_csrf(self):
        self.assertEqual(self.change('pausar', 999999).status_code, 404)
        self.assertEqual(self.client.patch(self.url+f'/{self.ids[0]}/pausar').status_code, 403)
        self.login(self.b)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.change('eliminar').status_code, 404)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_unlinked_shared_schedule_rejected_without_partial_change(self):
        with db.engine.begin() as conn:
            conn.execute(self.schedules.update().values(legacy_task_id=None))
        self.assertEqual(self.change('pausar').status_code, 409)
        self.assertEqual(self.change('eliminar').status_code, 409)
        self.assertTrue(all(t['state']=='active' for t in self.client.get(self.url).json['tasks']))

    def test_populated_task_link_mismatch_and_no_charges(self):
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE agente_tareas ADD COLUMN ae_agent_id VARCHAR(36) NULL'))
            conn.execute(text("UPDATE agente_tareas SET ae_agent_id = 'engine'"))
        self.assertEqual(self.change('pausar').status_code, 200)
        with db.engine.begin() as conn:
            self.assertEqual(conn.execute(text('SELECT ejecuciones_habilitadas FROM pwa_scraping_cupos')).scalar(), 6)
            self.assertEqual(conn.execute(text('SELECT COUNT(*) FROM pwa_scraping_operaciones')).scalar(), 0)
            conn.execute(text("UPDATE agente_tareas SET ae_agent_id = 'another-engine'"))
        self.assertEqual(self.change('activar').status_code, 409)

    def test_future_run_recomputed_and_bad_definition_rolls_back(self):
        self.change('pausar')
        with db.engine.begin() as conn:
            conn.execute(self.schedules.update().where(self.schedules.c.id == str(self.ids[0]))
                         .values(next_run_at=None))
        response = self.change('activar')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIsNotNone(response.json['tasks'][0]['schedules'][0]['next_run_at'])
        self.change('pausar')
        with db.engine.begin() as conn:
            conn.execute(self.schedules.update().where(self.schedules.c.id == str(self.ids[0]))
                         .values(next_run_at=None, definition={}))
        self.assertEqual(self.change('activar').status_code, 409)
        self.assertEqual(self.client.get(self.url).json['tasks'][0]['state'], 'paused')

    def test_real_usage_and_linked_job_history_retained(self):
        with db.engine.begin() as conn:
            conn.execute(text('CREATE TABLE agente_ejecucion_tareas (id INTEGER PRIMARY KEY, tarea_id INTEGER, puntos_consumidos INTEGER)'))
            conn.execute(text('INSERT INTO agente_ejecucion_tareas VALUES (1, :task, 3)'), {'task': self.ids[0]})
            conn.execute(text('CREATE TABLE ae_jobs (id TEXT PRIMARY KEY, owner_id INTEGER, agent_id TEXT, legacy_task_id INTEGER, started_at DATETIME)'))
            conn.execute(text("INSERT INTO ae_jobs VALUES ('job', :owner, 'engine', :task, '2026-11-01 09:00:00')"), {'owner': self.a, 'task': self.ids[0]})
        task = self.client.get(self.url).json['tasks'][0]
        self.assertEqual(task['points_consumed'], 3)
        self.assertEqual(task['last_run_at'], '2026-11-01T09:00:00')
        self.assertEqual(self.change('eliminar').status_code, 200)
        with db.engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT COUNT(*) FROM ae_jobs')).scalar(), 1)
            self.assertEqual(conn.execute(text('SELECT SUM(puntos_consumidos) FROM agente_ejecucion_tareas')).scalar(), 3)

    def test_task_editor_metadata_keeps_agent_configuration_readable(self):
        with db.engine.begin() as conn:
            params = dict(conn.execute(select(tareas.c.parametros).where(tareas.c.id == self.ids[0])).scalar())
            params['_agent_configuration'] = {'instructions':'Task-specific context'}
            params['_configuration_revision'] = 2
            conn.execute(tareas.update().where(tareas.c.id == self.ids[0]).values(parametros=params))
        response = self.client.get('/api/agente/configuracion')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['agent']['id'], self.agent_id)
        saved = self.save({**self.config, 'points':11}, 1)
        self.assertEqual(saved.status_code, 200, saved.json)
        with db.engine.connect() as conn:
            stored = conn.execute(select(tareas.c.parametros).where(tareas.c.id == self.ids[0])).scalar()
            self.assertEqual(stored['_configuration_revision'], 2)
            self.assertEqual(stored['_agent_configuration'], params['_agent_configuration'])
