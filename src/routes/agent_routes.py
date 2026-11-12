"""Authenticated configuration only. No activation, scheduling or execution routes."""
from urllib.parse import urlsplit
from flask import Blueprint, jsonify, request, session, current_app
from sqlalchemy.exc import SQLAlchemyError
from services.agent_configuration import AgentConfigurationStore, validate_config, verify_catalog
from services.query_preparation import PreparationError
from services.dpia_client import CatalogError, CatalogFiltersError

agent_bp=Blueprint('agent',__name__,url_prefix='/api/agente')


@agent_bp.after_request
def no_cache(response):
    response.headers['Cache-Control']='no-store'
    return response


@agent_bp.route('/configuracion',methods=['GET','PUT'])
def configuration():
    user_id=session.get('user_id')
    if type(user_id) is not int:
        return jsonify(success=False,error='Iniciá sesión para guardar tu agente.'),401
    store=current_app.extensions.get('agent_configuration_store') or AgentConfigurationStore()
    try:
        if request.method in ('GET','HEAD'):
            from services.agent_point_status import for_agent
            agent=store.get(user_id)
            return jsonify(success=True,agent=agent,points=for_agent(user_id,agent),execution_available=False)
        try:
            origin=request.headers.get('Origin')
            same_origin=not origin or urlsplit(origin).netloc==request.host
        except ValueError:same_origin=False
        if request.headers.get('X-DPIA-Action')!='configure-agent' or request.headers.get('Sec-Fetch-Site')=='cross-site' or not same_origin:
            return jsonify(success=False,error='Solicitud de configuración no autorizada.'),403
        if not request.is_json:
            return jsonify(success=False,error='Revisá la configuración del agente.'),415
        if request.content_length is not None and request.content_length>65536:
            return jsonify(success=False,error='Revisá la configuración del agente.'),413
        if len(request.get_data(cache=True))>65536:
            return jsonify(success=False,error='Revisá la configuración del agente.'),413
        body=request.get_json(silent=True)
        if not isinstance(body,dict) or set(body)!={'configuration','expected_revision'} or type(body['expected_revision']) is not int or not 0<=body['expected_revision']<=2147483646:
            return jsonify(success=False,error='Revisá la configuración del agente.'),400
        config=verify_catalog(validate_config(body['configuration']))
        agent=store.save(user_id,config,body['expected_revision'])
        return jsonify(success=True,agent=agent,execution_available=False)
    except PreparationError as exc:return jsonify(success=False,error=str(exc)),exc.status
    except (CatalogError,CatalogFiltersError):
        return jsonify(success=False,error='No se pudo verificar el catálogo del agente. Reintentá.'),502
    except SQLAlchemyError:
        current_app.logger.warning('Agent configuration database unavailable')
        return jsonify(success=False,error='No se confirmó el guardado del agente. Revisá las tablas y volvé a cargar su configuración.'),503


@agent_bp.post('/tareas')
def create_task():
    user_id = session.get('user_id')
    if type(user_id) is not int:
        return jsonify(success=False, error='Iniciá sesión.'), 401
    origin = request.headers.get('Origin')
    try:
        same_origin = not origin or urlsplit(origin).netloc == request.host
    except ValueError:
        same_origin = False
    if (request.headers.get('X-DPIA-Action') != 'create-task'
            or request.headers.get('Sec-Fetch-Site') == 'cross-site' or not same_origin):
        return jsonify(success=False, error='Solicitud no autorizada.'), 403
    if not request.is_json or (request.content_length or 0) > 65536:
        return jsonify(success=False, error='Consulta inválida.'), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {'configuration'}:
        return jsonify(success=False, error='Consulta inválida.'), 400
    try:
        config = verify_catalog(validate_config(body['configuration']))
        store = current_app.extensions.get('agent_configuration_store') or AgentConfigurationStore()
        task = store.add_task_to_existing_agent(user_id, config)
        return jsonify(success=True, task=task), 200 if task['duplicate'] else 201
    except PreparationError as exc:
        return jsonify(success=False, error=str(exc)), exc.status
    except (CatalogError, CatalogFiltersError):
        return jsonify(success=False, error='No se pudo verificar el catálogo.'), 502
    except SQLAlchemyError:
        current_app.logger.exception('Task creation failed')
        return jsonify(success=False, error='No se confirmó la creación de la tarea.'), 503


@agent_bp.post('/activar')
def activate():
    user_id=session.get('user_id')
    if type(user_id) is not int:
        return jsonify(success=False,error='Iniciá sesión para guardar tu agente.'),401
    try:
        origin=request.headers.get('Origin')
        same_origin=not origin or urlsplit(origin).netloc==request.host
    except ValueError:same_origin=False
    if request.headers.get('X-DPIA-Action')!='activate-agent' or request.headers.get('Sec-Fetch-Site')=='cross-site' or not same_origin:
        return jsonify(success=False,error='Solicitud de activación no autorizada.'),403
    if not request.is_json:return jsonify(success=False,error='Revisá la configuración del agente.'),415
    if (request.content_length or 0)>1024 or len(request.get_data(cache=True))>1024:
        return jsonify(success=False,error='Revisá la configuración del agente.'),413
    body=request.get_json(silent=True)
    if (not isinstance(body,dict) or set(body)!={'expected_revision'}
            or type(body['expected_revision']) is not int or not 1<=body['expected_revision']<=2147483646):
        return jsonify(success=False,error='Revisá la configuración del agente.'),400
    store=current_app.extensions.get('agent_configuration_store') or AgentConfigurationStore()
    try:
        return jsonify(success=True,agent=store.activate(user_id,body['expected_revision']),execution_available=False)
    except PreparationError as exc:return jsonify(success=False,error=str(exc)),exc.status
    except SQLAlchemyError:
        current_app.logger.warning('Agent activation database unavailable')
        return jsonify(success=False,error='No se confirmó la activación. Reintentá; no se creará un duplicado.'),503
