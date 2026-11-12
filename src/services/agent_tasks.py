"""Manage configured tasks only. Never submits jobs or touches credits/history."""
from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from model.agent_tasks import AgentTaskRepository
from services.agent_configuration import bad


def deleted(task):
    return bool((task['parametros'] or {}).get('_deleted_at'))


def iso(value):
    return value.isoformat() if value is not None else None


def next_run(schedule, now):
    if schedule['next_run_at'] and schedule['next_run_at'] > now:
        return schedule['next_run_at']
    definition = schedule['definition'] or {}
    try:
        zone = ZoneInfo(schedule['timezone'])
        clock = time.fromisoformat(definition['execution_time'])
        if definition['frequency'] not in ('DAILY', 'WEEKLY'):
            raise ValueError()
        local = now.replace(tzinfo=timezone.utc).astimezone(zone)
        for offset in range(8):
            day = local.date() + timedelta(days=offset)
            if definition['frequency'] == 'WEEKLY' and day.isoweekday() not in definition['weekdays']:
                continue
            candidate = datetime.combine(day, clock, zone).astimezone(timezone.utc).replace(tzinfo=None)
            if candidate > now:
                return candidate
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
        pass
    bad('La próxima ejecución requiere actualizar su programación.', 409)


class AgentTaskService:
    def __init__(self, repository=None):
        self.repository = repository or AgentTaskRepository()

    def handle(self, owner, agent_id, task_id=None, action=None):
        repo = self.repository
        with repo.transaction(owner, agent_id) as (conn, tables, agent):
            tasks = repo.tasks(conn, tables, agent_id)
            engines = repo.engines(conn, tables, owner, agent_id)
            if len(engines) > 1:
                bad('El vínculo de las tareas requiere revisión.', 409)
            engine = engines[0] if engines else None
            schedules = repo.schedules(conn, tables, owner, engine['id']) if engine else []
            for task in tasks:
                if task.get('ae_agent_id') and (not engine or task['ae_agent_id'] != engine['id']):
                    bad('El vínculo de las tareas requiere revisión.', 409)
            legacy = repo.legacy_schedules(conn, tables, agent_id)
            if action:
                task = next((t for t in tasks if t['id'] == task_id), None)
                if task is None:
                    bad('Tarea no disponible.', 404)
                if deleted(task):
                    if action != 'eliminar':
                        bad('Tarea no disponible.', 404)
                else:
                    # Never guess which task an unlinked/shared schedule executes.
                    if any(s['activa'] for s in legacy) or any(s.get('legacy_task_id') is None for s in schedules):
                        bad('La programación compartida requiere vincular cada tarea.', 409)
                    linked = [s for s in schedules if s.get('legacy_task_id') == task_id]
                    enabled = action == 'activar'
                    if enabled and engine and not linked:
                        bad('La programación compartida requiere vincular cada tarea.', 409)
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    params = dict(task['parametros'] or {})
                    if action == 'eliminar':
                        params['_deleted_at'] = now.isoformat()
                    repo.change(conn, tables['agente_tareas'], task_id,
                                habilitada=enabled, parametros=params, actualizado_en=now)
                    for schedule in linked:
                        if bool(schedule['enabled']) != enabled:
                            repo.change(conn, tables['ae_schedules'], schedule['id'],
                                        enabled=enabled, revision=schedule['revision'] + 1,
                                        **({'next_run_at': next_run(schedule, now)} if enabled else {}))
                    tasks = repo.tasks(conn, tables, agent_id)
                    schedules = repo.schedules(conn, tables, owner, engine['id']) if engine else []
            consumption = repo.consumed(conn, [t['id'] for t in tasks])
            last_runs = repo.last_runs(conn, owner, engine['id'] if engine else None, [t['id'] for t in tasks])
            result = []
            for task in tasks:
                if deleted(task):
                    continue
                linked = [s for s in schedules if s.get('legacy_task_id') == task['id']]
                timing = []
                for s in linked:
                    definition = s['definition'] or {}
                    timing.append(dict(frequency=definition.get('frequency'), days=list(range(1, 8)) if definition.get('frequency') == 'DAILY' else definition.get('weekdays'),
                                       time=definition.get('execution_time'), timezone=s['timezone'],
                                       next_run_at=iso(s['next_run_at']) if s['enabled'] and task['habilitada'] else None))
                if not timing:
                    timing = [dict(frequency=s['frecuencia'], days=s['dias_semana'], time=iso(s['hora_local']),
                                   timezone=s['zona_horaria'], next_run_at=None) for s in legacy]
                result.append(dict(id=task['id'], name=task['nombre'], type=task['tipo'],
                                   state='active' if task['habilitada'] else 'paused', schedules=timing,
                                   last_run_at=iso(max(filter(None, [task['ultima_ejecucion_en'], last_runs.get(task['id'])]), default=None)), points_consumed=float(consumption[task['id']]) if consumption.get(task['id']) is not None else None))
            return result
