"""Read delivered agent results using the existing internal HMAC credential."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlsplit
import requests
from flask import current_app
from services.agent_configuration import bad

PATH='/api/agents/v1/internal/pwa-history'


def read_agent_history(owner_id, *, offset=0, job_id=None, review=None, task_action=None, configuration=None):
    base=current_app.config.get('AGENTS_INTERNAL_URL','').rstrip('/')
    key=current_app.config.get('PWA_ACTIVATION_SECRET','')
    parsed=urlsplit(base)
    if (not key or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        bad('La conexión con el historial de Agents no está configurada.',503)
    body={'owner_id':owner_id,**({'job_id':job_id} if job_id is not None else {'offset':offset})}
    if review is not None:body['review']=review
    if task_action is not None:body['task_action']=task_action
    if configuration is not None:body['configuration']=configuration
    raw=json.dumps(body,sort_keys=True,separators=(',',':')).encode();stamp=str(int(time.time()))
    signature=hmac.new(key.encode(),stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    try:
        response=requests.post(base+PATH,data=raw,headers={'Content-Type':'application/json',
            'X-DPIA-Timestamp':stamp,'X-DPIA-Signature':signature},timeout=(3.05,15),allow_redirects=False)
        if response.status_code in (400,403,404,409):
            code=response.json().get('error','')
            messages={'result_feedback_conflict':'Este resultado ya tiene otra decisión registrada. Actualizá su estado.',
                      'stale_review_result':'El resultado cambió. Actualizá su estado antes de revisarlo.',
                      'result_feedback_not_allowed':'Este resultado no admite revisión humana.',
                      'task_has_active_executions':'La tarea tiene otras ejecuciones activas. Esperá a que terminen.',
                      'revision_conflict':'La tarea cambió. Volvé a cargarla antes de guardar.'}
            bad(messages.get(code,'La respuesta o la acción todavía no está disponible.'),response.status_code)
        response.raise_for_status();data=response.json()
        if data.get('api_version')!='agents.v1' or type(data.get('owner_id')) is not int or data['owner_id']!=owner_id:raise ValueError()
        if task_action is not None:
            if data.get('job_id')!=job_id:raise ValueError()
        elif job_id is not None:
            if data.get('job_id')!=job_id or not (isinstance(data.get('result'),dict) or data.get('result_classification')=='TECHNICAL_ERROR' and data.get('result') is None) or not isinstance(data.get('agent_name'),str):raise ValueError()
        elif (not isinstance(data.get('operations'),list) or type(data.get('has_more')) is not bool
                or type(data.get('next_offset')) is not int or not offset<=data['next_offset']<=offset+24):raise ValueError()
        return data
    except (requests.RequestException,ValueError,TypeError,KeyError):
        bad('No se pudo consultar el historial de Agents. Reintentá.',502)
