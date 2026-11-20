"""VIDEO_GENERAR preferences stored in the existing task JSON (no duplicate tables)."""
from datetime import datetime, timezone
from model.agent_tasks import AgentTaskRepository
from services.agent_configuration import bad

SCRIPT_DEFAULTS = {'instructions': '', 'custom_script': ''}
PRODUCTION_DEFAULTS = {'video_type': 'news', 'duration_seconds': 60, 'language': 'es',
                       'format': '16:9', 'provider': 'heygen', 'avatar_id': 'auto',
                       'voice_id': 'auto', 'background': {'type':'auto'}, 'budget_credits': 20, 'automatic_production': False}


def read_section(video, section):
    defaults = SCRIPT_DEFAULTS if section == 'script' else PRODUCTION_DEFAULTS
    saved = video.get(section)
    result = {**defaults, **(saved if isinstance(saved, dict) else {})}
    if section == 'production':
        for field in ('duration_seconds', 'language', 'format', 'provider', 'avatar_id', 'voice_id', 'budget_credits', 'automatic_production', 'video_type'):
            if field not in (saved if isinstance(saved, dict) else {}) and field in video:
                result[field] = video[field]
        if result['budget_credits'] == 0:
            result['budget_credits'] = 20
    return result


def validate(section, values):
    defaults = SCRIPT_DEFAULTS if section == 'script' else PRODUCTION_DEFAULTS
    if not isinstance(values, dict) or set(values) - set(defaults):
        bad('Campos de configuración inválidos.', 422)
    result = {**defaults, **values}
    if section == 'script':
        if any(not isinstance(result[k], str) or len(result[k]) > limit for k, limit in [('instructions', 5000), ('custom_script', 20000)]):
            bad('Guion o instrucciones inválidos.', 422)
    else:
        if (type(result['duration_seconds']) is not int or not 1 <= result['duration_seconds'] <= 3600
            or type(result['budget_credits']) is not int or not 0 <= result['budget_credits'] <= 1000000
            or type(result['automatic_production']) is not bool):
            bad('Duración, presupuesto o autorización inválidos.', 422)
        for key in ('video_type', 'language', 'format', 'provider', 'avatar_id', 'voice_id'):
            if not isinstance(result[key], str) or not 1 <= len(result[key]) <= (160 if key in ('avatar_id','voice_id') else 100):
                bad('Configuración audiovisual inválida.', 422)
        import re
        if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',result[k]) for k in ('avatar_id','voice_id')):
            bad('Identificador audiovisual inválido.',422)
        background=result['background']
        if not isinstance(background,dict) or background.get('type') not in ('auto','color','image'):
            bad('Fondo inválido.',422)
        if background['type']=='auto' and set(background)!={'type'}:bad('Fondo inválido.',422)
        if background['type']=='color' and (set(background)!={'type','value'} or not isinstance(background.get('value'),str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',background['value'])):bad('Fondo inválido.',422)
        if background['type']=='image':
            from urllib.parse import urlsplit
            try:url=urlsplit(background.get('url',''))
            except (ValueError,TypeError):bad('Fondo inválido.',422)
            try:port=url.port
            except ValueError:bad('Fondo inválido.',422)
            host=(url.hostname or '').lower()
            if set(background)!={'type','url'} or url.scheme!='https' or not (host=='dpia.site' or host.endswith('.dpia.site')) or url.username or url.password or port not in (None,443) or len(background['url'])>2048:bad('Fondo inválido.',422)
    return result


class VideoTaskPreferences:
    def __init__(self, repository=None):
        self.repository = repository or AgentTaskRepository()

    def section(self, owner, agent_id, task_id, section, command=None):
        if section not in ('script', 'production'):
            bad('Sección de video inexistente.', 404)
        with self.repository.transaction(owner, agent_id) as (conn, tables, agent):
            task = next((t for t in self.repository.tasks(conn, tables, agent_id) if t['id'] == task_id), None)
            if not task or task['tipo'] != 'VIDEO_GENERAR' or (task['parametros'] or {}).get('_deleted_at'):
                bad('Tarea de video no disponible.', 404)
            params = dict(task['parametros'] or {})
            revision = params.get('_configuration_revision', 1)
            video = dict(params.get('video') or {})
            if command is not None:
                if (not isinstance(command, dict) or type(command.get('expected_revision')) is not int
                    or command['expected_revision'] != revision or not isinstance(command.get('values'), dict)):
                    bad('La configuración cambió. Actualizá antes de guardar.', 409)
                supplied=dict(command['values'])
                if section=='production' and 'background' not in supplied:
                    supplied['background']=read_section(video,section)['background']
                video[section] = validate(section, supplied)
                params['video'] = video
                params['_configuration_revision'] = revision + 1
                self.repository.change(conn, tables['agente_tareas'], task_id, parametros=params,
                                       actualizado_en=datetime.now(timezone.utc).replace(tzinfo=None))
                revision += 1
            return {'revision': revision, 'section': section, 'values': read_section(video, section)}
