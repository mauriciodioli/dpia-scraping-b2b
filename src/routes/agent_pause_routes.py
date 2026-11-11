"""Owner-only pause/status bridge; activation and local configuration stay unchanged."""
import hashlib
import hmac
import json
import time
from uuid import UUID
from urllib.parse import urlsplit
import requests
from flask import Blueprint,current_app,jsonify,request,session
from sqlalchemy.exc import SQLAlchemyError
from services.agent_configuration import AgentConfigurationStore,bad
from services.query_preparation import PreparationError

pause_bp=Blueprint('agent_pause',__name__)
PATH='/api/agents/v1/internal/pwa-pause'


def read_pause(user_id,command=None):
    store=current_app.extensions.get('agent_configuration_store') or AgentConfigurationStore()
    agent=store.get(user_id)
    if agent is None and command is None:return None
    if not agent or agent['state']!='active':bad('Activá tu agente antes de pausarlo.',409)
    binding=agent['configuration'].get('engine_binding')
    if not isinstance(binding,dict) or not binding.get('id'):bad('El vínculo del agente no es válido.',409)
    base=current_app.config.get('AGENTS_INTERNAL_URL','').rstrip('/')
    secret=current_app.config.get('PWA_ACTIVATION_SECRET','')
    parsed=urlsplit(base)
    if (not secret or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        bad('La conexión interna del agente no está configurada.',503)
    payload=dict(owner_id=user_id,source_agent_id=agent['id'],agent_id=binding['id'],command=command)
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    stamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    try:
        response=requests.post(base+PATH,data=raw,headers={'Content-Type':'application/json',
            'X-DPIA-Timestamp':stamp,'X-DPIA-Signature':signature},timeout=(3.05,15),allow_redirects=False)
        result=response.json()
        if response.status_code in (403,409):
            errors={'administrator_pause_active':'El administrador mantiene el agente pausado.',
                    'revision_conflict':'El estado cambió. Actualizá el agente antes de reintentar.'}
            bad(errors.get(result.get('error'),'El servicio no autorizó el cambio de estado.'),response.status_code)
        if response.status_code!=200:bad('No se confirmó el estado del agente. Reintentá.',502)
        remote=result['agent'];flags=remote['pause']
        if (result['api_version']!='agents.v1' or type(result['owner_id']) is not int or result['owner_id']!=user_id
                or type(result['source_agent_id']) is not int or result['source_agent_id']!=agent['id']
                or remote['id']!=binding['id'] or result['execution_enabled'] is not False
                or type(remote['revision']) is not int or remote['revision']<1
                or set(flags)!={'user_paused','admin_paused'} or any(type(v) is not bool for v in flags.values())
                or remote['configuration_state'] not in ('ENABLED','DISABLED')):
            raise ValueError()
    except (requests.RequestException,ValueError,KeyError,TypeError,AttributeError):
        bad('No se confirmó el estado del agente. Reintentá.',502)
    state='admin_paused' if flags['admin_paused'] else 'paused' if flags['user_paused'] else (
        'active' if remote['configuration_state']=='ENABLED' else 'disabled')
    return {**agent,'state':state,'engine_revision':remote['revision'],'pause':flags}


@pause_bp.after_request
def no_cache(response):
    response.headers['Cache-Control']='no-store'
    return response


@pause_bp.route('/api/agente/pausa',methods=['GET','POST'])
def pause():
    user_id=session.get('user_id')
    if type(user_id) is not int:return jsonify(success=False,error='Iniciá sesión.'),401
    command=None
    if request.method=='POST':
        try:
            origin=request.headers.get('Origin')
            same_origin=not origin or urlsplit(origin).netloc==request.host
        except ValueError:same_origin=False
        if request.headers.get('X-DPIA-Action')!='pause-agent' or request.headers.get('Sec-Fetch-Site')=='cross-site' or not same_origin:
            return jsonify(success=False,error='Solicitud de pausa no autorizada.'),403
        if not request.is_json:return jsonify(success=False,error='Revisá la solicitud.'),415
        if (request.content_length or 0)>1024 or len(request.get_data(cache=True))>1024:
            return jsonify(success=False,error='Revisá la solicitud.'),413
        command=request.get_json(silent=True)
        try:
            if (not isinstance(command,dict) or set(command)!={'paused','expected_revision','operation_id'}
                    or type(command['paused']) is not bool or type(command['expected_revision']) is not int
                    or command['expected_revision']<1 or str(UUID(command['operation_id']))!=command['operation_id']):
                raise ValueError()
        except (ValueError,TypeError,AttributeError):
            return jsonify(success=False,error='Revisá la solicitud.'),400
    try:
        return jsonify(success=True,agent=read_pause(user_id,command),execution_available=False)
    except PreparationError as exc:return jsonify(success=False,error=str(exc)),exc.status
    except SQLAlchemyError:
        current_app.logger.warning('Agent pause database unavailable')
        return jsonify(success=False,error='No se confirmó el estado del agente. Reintentá.'),503
