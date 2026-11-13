"""Repository over existing shared tables; reflection never executes DDL."""
from contextlib import contextmanager
from sqlalchemy import MetaData, Table, select, update, inspect, func
from model.usuario import Usuario
from utils.db import db
from services.query_preparation import PreparationError


def bad(message, status):
    raise PreparationError(message, status)


class AgentTaskRepository:
    def __init__(self, engine=None):
        self.engine = engine

    @contextmanager
    def transaction(self, owner, agent_id):
        engine = self.engine or db.engine
        if self.engine is None and engine.dialect.name != "mysql":
            bad("La administración de tareas requiere MySQL.", 503)
        with engine.begin() as conn:
            if conn.execute(select(Usuario.id).where(Usuario.id == owner, Usuario.activo.is_(True)).with_for_update()).first() is None:
                bad("Iniciá sesión.", 401)
            metadata = MetaData()
            tables = {name: Table(name, metadata, autoload_with=conn, resolve_fks=False)
                      for name in ('agentes', 'agente_tareas', 'agente_programaciones',
                                   'ae_agents', 'ae_schedules')}
            a = tables['agentes']
            agent = conn.execute(select(a).where(a.c.id == agent_id, a.c.usuario_id == owner)
                                 .with_for_update()).mappings().first()
            if not agent or (agent['configuracion'] or {}).get('_deleted_at'):
                bad('Agente no disponible.', 404)
            yield conn, tables, agent

    @staticmethod
    def tasks(conn, tables, agent_id):
        t = tables['agente_tareas']
        return conn.execute(select(t).where(t.c.agente_id == agent_id)
                            .order_by(t.c.id).with_for_update()).mappings().all()

    @staticmethod
    def engines(conn, tables, owner, agent_id):
        a = tables['ae_agents']
        return conn.execute(select(a).where(a.c.legacy_agent_id == agent_id,
                            a.c.owner_id == owner).with_for_update()).mappings().all()

    @staticmethod
    def paused(conn, engine):
        if not engine:
            return False
        if engine.get('configuration_state') == 'DISABLED':
            return True
        if not inspect(conn).has_table('ae_agent_events'):
            return False
        events = Table('ae_agent_events', MetaData(), autoload_with=conn, resolve_fks=False)
        flags = conn.execute(select(events.c.details).where(
            events.c.owner_id == engine['owner_id'], events.c.agent_id == engine['id'],
            events.c.action == 'AGENT_PAUSE_CHANGED').order_by(events.c.revision.desc()).limit(1)).scalar()
        return bool(flags and (flags.get('user_paused') or flags.get('admin_paused')))

    @staticmethod
    def schedules(conn, tables, owner, engine_id):
        s = tables['ae_schedules']
        return conn.execute(select(s).where(s.c.owner_id == owner, s.c.agent_id == engine_id)
                            .with_for_update()).mappings().all()

    @staticmethod
    def change(conn, table, row_id, **values):
        conn.execute(update(table).where(table.c.id == row_id).values(**values))

    @staticmethod
    def legacy_schedules(conn, tables, agent_id):
        p = tables['agente_programaciones']
        return conn.execute(select(p).where(p.c.agente_id == agent_id)).mappings().all()

    @staticmethod
    def consumed(conn, task_ids):
        # Only show a measured total when the deployed legacy schema exposes it.
        if not task_ids or not inspect(conn).has_table('agente_ejecucion_tareas'):
            return {}
        detail = Table('agente_ejecucion_tareas', MetaData(), autoload_with=conn, resolve_fks=False)
        if not {'tarea_id', 'puntos_consumidos'}.issubset(detail.c.keys()):
            return {}
        return dict(conn.execute(select(detail.c.tarea_id, func.sum(detail.c.puntos_consumidos))
                    .where(detail.c.tarea_id.in_(task_ids)).group_by(detail.c.tarea_id)).all())

    @staticmethod
    def last_runs(conn, owner, engine_id, task_ids):
        if not engine_id or not task_ids or not inspect(conn).has_table('ae_jobs'):
            return {}
        jobs = Table('ae_jobs', MetaData(), autoload_with=conn, resolve_fks=False)
        if not {'legacy_task_id', 'started_at', 'owner_id', 'agent_id'}.issubset(jobs.c.keys()):
            return {}
        return dict(conn.execute(select(jobs.c.legacy_task_id, func.max(jobs.c.started_at))
                    .where(jobs.c.owner_id == owner, jobs.c.agent_id == engine_id,
                           jobs.c.legacy_task_id.in_(task_ids)).group_by(jobs.c.legacy_task_id)).all())

    @staticmethod
    def execution_history(conn, owner, engine_id, task_ids):
        if not engine_id or not task_ids or not inspect(conn).has_table('ae_jobs'):
            return {}
        jobs=Table('ae_jobs',MetaData(),autoload_with=conn,resolve_fks=False)
        columns=('id','legacy_task_id','state','error_code','created_at','started_at','finished_at')
        if not set(columns).issubset(jobs.c.keys()):return {}
        rows=conn.execute(select(*(jobs.c[key] for key in columns)).where(
            jobs.c.owner_id==owner,jobs.c.agent_id==engine_id,jobs.c.legacy_task_id.in_(task_ids))
            .order_by(jobs.c.created_at.desc(),jobs.c.id.desc()).limit(100)).mappings().all()
        history={};runs={}
        for row in rows:
            items=history.setdefault(row['legacy_task_id'],[])
            if len(items)>=5:continue
            run={key:row[key].isoformat() if row[key] is not None else None for key in ('created_at','started_at','finished_at')}
            run.update(id=row['id'],state=row['state'],reason_code=row['error_code'],steps=[])
            items.append(run);runs[row['id']]=run
        if runs and inspect(conn).has_table('ae_tasks'):
            tasks=Table('ae_tasks',MetaData(),autoload_with=conn,resolve_fks=False)
            steps=conn.execute(select(tasks.c.id,tasks.c.job_id,tasks.c.tool_id,tasks.c.state,tasks.c.provider_submission_state)
                .where(tasks.c.owner_id==owner,tasks.c.job_id.in_(runs)).order_by(tasks.c.position).limit(1000)).mappings().all()
            errors={}
            if steps and inspect(conn).has_table('ae_attempts'):
                attempts=Table('ae_attempts',MetaData(),autoload_with=conn,resolve_fks=False)
                for row in conn.execute(select(attempts.c.task_id,attempts.c.error_code).where(
                    attempts.c.owner_id==owner,attempts.c.task_id.in_([s['id'] for s in steps]),attempts.c.error_code.is_not(None))
                    .order_by(attempts.c.number.desc()).limit(1000)).mappings():
                    errors.setdefault(row['task_id'],row['error_code'])
            for step in steps:
                runs[step['job_id']]['steps'].append(dict(tool=step['tool_id'],state=step['state'],
                    submitted=step['provider_submission_state']!='NOT_SUBMITTED',reason_code=errors.get(step['id'])))
        return history
