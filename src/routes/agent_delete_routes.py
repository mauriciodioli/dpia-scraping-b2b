"""Owner-only B2B bridge to central logical deletion; no browser-supplied target IDs."""
import hashlib,hmac,json,time
from uuid import UUID
from urllib.parse import urlsplit
import requests
from flask import Blueprint,current_app,jsonify,request,session
from sqlalchemy.exc import SQLAlchemyError
from services.agent_configuration import AgentConfigurationStore,bad
from services.query_preparation import PreparationError

delete_bp=Blueprint('agent_delete',__name__)
PATH='/api/agents/v1/internal/pwa-delete'


def delete_owned(user_id,command):
    store=current_app.extensions.get('agent_configuration_store') or AgentConfigurationStore()
    agent=store.get(user_id)
    if agent is None:return None
    if agent['revision']!=command['expected_revision']:bad('La configuración cambió. Volvé a cargarla.',409)
    binding=agent['configuration'].get('engine_binding') or {}
    base=current_app.config.get('AGENTS_INTERNAL_URL','').rstrip('/');secret=current_app.config.get('PWA_ACTIVATION_SECRET','')
    parsed=urlsplit(base)
    if (not secret or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or
            parsed.password or parsed.path or parsed.query or parsed.fragment):bad('La conexión interna del agente no está configurada.',503)
    payload=dict(owner_id=user_id,source_agent_id=agent['id'],source_revision=agent['revision'],agent_id=binding.get('id'),
        command=dict(confirm=True,operation_id=command['operation_id'],expected_revision=command['engine_revision'] or agent['revision']))
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode();stamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    try:
        response=requests.post(base+PATH,data=raw,headers={'Content-Type':'application/json',
            'X-DPIA-Timestamp':stamp,'X-DPIA-Signature':signature},timeout=(3.05,15),allow_redirects=False)
        data=response.json()
        if response.status_code==409:bad('No se puede eliminar: hay trabajos activos o cambió la configuración.',409)
        if response.status_code!=200:bad('No se confirmó la eliminación. Reintentá.',502)
        if (data['api_version']!='agents.v1' or data['deleted'] is not True or type(data['owner_id']) is not int
                or data['owner_id']!=user_id or data['execution_enabled'] is not False or type(data['source_agent_id']) is not int):
            raise ValueError()
    except (requests.RequestException,ValueError,KeyError,TypeError):bad('No se confirmó la eliminación. Reintentá.',502)
    remaining=store.get(user_id)
    if remaining and remaining['id']==agent['id'] and remaining['revision']==agent['revision']:
        bad('No se confirmó la limpieza de la configuración B2B. Reintentá.',502)
    return remaining


@delete_bp.post('/api/agente/eliminar')
def delete():
    user_id=session.get('user_id')
    if type(user_id) is not int:return jsonify(success=False,error='Iniciá sesión.'),401
    try:
        origin=request.headers.get('Origin');same=not origin or urlsplit(origin).netloc==request.host
    except ValueError:same=False
    if not same or request.headers.get('Sec-Fetch-Site')=='cross-site' or request.headers.get('X-DPIA-Action')!='delete-agent':
        return jsonify(success=False,error='Solicitud no autorizada.'),403
    if not request.is_json:return jsonify(success=False,error='Revisá la solicitud.'),415
    if (request.content_length or 0)>1024 or len(request.get_data(cache=True))>1024:return jsonify(success=False,error='Solicitud demasiado grande.'),413
    command=request.get_json(silent=True)
    try:
        if (not isinstance(command,dict) or set(command)!={'confirm','expected_revision','engine_revision','operation_id'} or
                command['confirm'] is not True or type(command['expected_revision']) is not int or command['expected_revision']<1 or
                (command['engine_revision'] is not None and (type(command['engine_revision']) is not int or command['engine_revision']<1)) or
                str(UUID(command['operation_id']))!=command['operation_id']):raise ValueError()
    except (ValueError,TypeError,AttributeError):return jsonify(success=False,error='Revisá la solicitud.'),400
    try:return jsonify(success=True,agent=delete_owned(user_id,command),execution_available=False)
    except PreparationError as exc:return jsonify(success=False,error=str(exc)),exc.status
    except SQLAlchemyError:return jsonify(success=False,error='No se confirmó la eliminación. Reintentá.'),503

@delete_bp.after_request
def no_cache(response):response.headers['Cache-Control']='no-store';return response
