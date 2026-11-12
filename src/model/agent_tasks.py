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
