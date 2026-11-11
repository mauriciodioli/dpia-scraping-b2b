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


def read_agent_history(owner_id, *, offset=0, job_id=None):
    base=current_app.config.get('AGENTS_INTERNAL_URL','').rstrip('/')
    key=current_app.config.get('PWA_ACTIVATION_SECRET','')
    parsed=urlsplit(base)
    if (not key or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        bad('La conexión con el historial de Agents no está configurada.',503)
    body={'owner_id':owner_id,**({'job_id':job_id} if job_id is not None else {'offset':offset})}
    raw=json.dumps(body,sort_keys=True,separators=(',',':')).encode();stamp=str(int(time.time()))
    signature=hmac.new(key.encode(),stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    try:
        response=requests.post(base+PATH,data=raw,headers={'Content-Type':'application/json',
            'X-DPIA-Timestamp':stamp,'X-DPIA-Signature':signature},timeout=(3.05,15),allow_redirects=False)
        if response.status_code in (404,409):bad('La respuesta del agente todavía no está disponible.',response.status_code)
        response.raise_for_status();data=response.json()
        if data.get('api_version')!='agents.v1' or type(data.get('owner_id')) is not int or data['owner_id']!=owner_id:raise ValueError()
        if job_id is not None:
            if data.get('job_id')!=job_id or not isinstance(data.get('result'),dict) or not isinstance(data.get('agent_name'),str):raise ValueError()
        elif (not isinstance(data.get('operations'),list) or type(data.get('has_more')) is not bool
                or type(data.get('next_offset')) is not int or not offset<=data['next_offset']<=offset+24):raise ValueError()
        return data
    except (requests.RequestException,ValueError,TypeError,KeyError):
        bad('No se pudo consultar el historial de Agents. Reintentá.',502)
