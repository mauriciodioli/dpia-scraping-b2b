"""Authenticated HTTP controller for configured tasks."""
from urllib.parse import urlsplit
from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy.exc import SQLAlchemyError
from services.agent_tasks import AgentTaskService
from services.query_preparation import PreparationError

task_bp = Blueprint('agent_tasks', __name__)


@task_bp.post('/api/agentes/<int:agent_id>/tareas/<int:task_id>/ejecutar')
def run_video_task(agent_id,task_id):
    from uuid import UUID
    owner=session.get('user_id')
    if type(owner) is not int:return jsonify(success=False,error='Iniciá sesión.'),401
    try:
        origin=request.headers.get('Origin')
        if request.headers.get('X-DPIA-Action')!='execute-task' or request.headers.get('Sec-Fetch-Site')=='cross-site' or (origin and urlsplit(origin).netloc!=request.host):
            return jsonify(success=False,error='Solicitud no autorizada.'),403
        if not request.is_json or (request.content_length or 0)>1024:return jsonify(success=False,error='Solicitud inválida.'),400
        body=request.get_json(silent=True)
        if not isinstance(body,dict) or set(body)!={'request_id'} or str(UUID(body['request_id']))!=body['request_id']:
            return jsonify(success=False,error='Solicitud inválida.'),400
        from services.agent_activation import schedule_immediate_task
        result=schedule_immediate_task(owner,agent_id,task_id,body['request_id'],existing=True)
        return jsonify(success=True,**result),202
    except (ValueError,TypeError,KeyError,AttributeError):return jsonify(success=False,error='Solicitud inválida.'),400
    except PreparationError as exc:return jsonify(success=False,error=str(exc)),exc.status
    except SQLAlchemyError:return jsonify(success=False,error='No se confirmó la ejecución.'),503


@task_bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@task_bp.get('/api/agentes/<int:agent_id>/tareas')
@task_bp.patch('/api/agentes/<int:agent_id>/tareas/<int:task_id>/<action>')
@task_bp.delete('/api/agentes/<int:agent_id>/tareas/<int:task_id>')
def tasks(agent_id, task_id=None, action=None):
    owner = session.get('user_id')
    if type(owner) is not int:
        return jsonify(success=False, error='Iniciá sesión.'), 401
    if request.method != 'GET':
        if request.method == 'DELETE':
            action = 'eliminar'
        if action not in (('eliminar',) if request.method == 'DELETE' else ('activar', 'pausar', 'renombrar', 'programar')):
            return jsonify(success=False, error='Acción no disponible.'), 404
        try:
            origin = request.headers.get('Origin')
            same = not origin or urlsplit(origin).netloc == request.host
        except ValueError:
            same = False
        if not same or request.headers.get('Sec-Fetch-Site') == 'cross-site' or request.headers.get('X-DPIA-Action') != 'manage-task':
            return jsonify(success=False, error='Solicitud no autorizada.'), 403
    try:
        service = current_app.extensions.get('agent_task_service') or AgentTaskService()
        command = None
        if action == 'programar':
            if not request.is_json or (request.content_length or 0)>4096:
                return jsonify(success=False,error='Programación inválida.'),400
            command=request.get_json(silent=True)
            if not isinstance(command,dict):
                return jsonify(success=False,error='Programación inválida.'),400
        if action == 'renombrar':
            if not request.is_json or (request.content_length or 0) > 4096:
                return jsonify(success=False, error='Nombre inválido.'), 400
            command = request.get_json(silent=True)
            if (not isinstance(command, dict) or set(command) != {'name', 'expected_revision'}
                    or type(command['expected_revision']) is not int or command['expected_revision'] < 1):
                return jsonify(success=False, error='Nombre o revisión inválidos.'), 400
        items = service.handle(owner, agent_id, task_id, action, command) if command is not None else service.handle(owner, agent_id, task_id, action)
        return jsonify(success=True, tasks=items, count=len(items), execution_available=False)
    except PreparationError as exc:
        return jsonify(success=False, error=str(exc)), exc.status
    except SQLAlchemyError:
        current_app.logger.warning('Agent task storage unavailable')
        return jsonify(success=False, error='No se confirmó el cambio de tareas. Reintentá.'), 503


@task_bp.route('/api/agentes/<int:agent_id>/tareas/<int:task_id>/video/<section>', methods=['GET', 'PATCH'])
def video_preferences(agent_id, task_id, section):
    from services.video_task_preferences import VideoTaskPreferences
    owner = session.get('user_id')
    if type(owner) is not int:
        return jsonify(success=False, error='Iniciá sesión.'), 401
    if request.method == 'PATCH':
        try:
            origin = request.headers.get('Origin')
            same = not origin or urlsplit(origin).netloc == request.host
        except ValueError:
            same = False
        if not same or request.headers.get('Sec-Fetch-Site') == 'cross-site' or request.headers.get('X-DPIA-Action') != 'manage-task':
            return jsonify(success=False, error='Solicitud no autorizada.'), 403
        if not request.is_json or (request.content_length or 0) > 30000:
            return jsonify(success=False, error='Configuración inválida.'), 400
        command = request.get_json(silent=True)
        if not isinstance(command, dict) or set(command) != {'expected_revision', 'values'}:
            return jsonify(success=False, error='Configuración inválida.'), 400
    else:
        command = None
    try:
        return jsonify(success=True, **VideoTaskPreferences().section(owner, agent_id, task_id, section, command))
    except PreparationError as exc:
        return jsonify(success=False, error=str(exc)), exc.status
    except SQLAlchemyError:
        current_app.logger.warning('Video preferences storage unavailable')
        return jsonify(success=False, error='No se pudo acceder a la configuración.'), 503
