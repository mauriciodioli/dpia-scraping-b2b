"""Translate only compatible saved configurations and confirm remote provisioning."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlsplit
import requests
from flask import current_app
from services.agent_configuration import bad
from services.task_names import normalize_task_payload

PATH = '/api/agents/v1/internal/pwa-activations'


def video_resources(user_id, agent_id, task_id, language):
    payload=dict(operation='video_resources',owner_id=user_id,source_agent_id=agent_id,task_id=task_id,language=language)
    base=current_app.config.get('AGENTS_INTERNAL_URL','').rstrip('/')
    secret=current_app.config.get('PWA_ACTIVATION_SECRET','');parsed=urlsplit(base)
    if not secret or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        bad('La conexión con Agents no está configurada.',503)
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode();stamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    try:
        response=requests.post(base+PATH,data=raw,headers={'Content-Type':'application/json','X-DPIA-Timestamp':stamp,'X-DPIA-Signature':signature},timeout=(3.05,30),allow_redirects=False)
        data=response.json()
        if response.status_code!=200:
            error=data.get('error');code=error.get('code') if isinstance(error,dict) else error
            bad('No se pudo consultar el catálogo de video'+(': '+code if isinstance(code,str) else '')+'.',502)
        if not isinstance(data,dict) or any(not isinstance(data.get(key),list) for key in ('avatars','voices','errors')):raise ValueError()
        return data
    except (requests.RequestException,ValueError,TypeError):
        bad('No se pudo consultar el catálogo de video. Reintentá.',502)


def translate(agent, user_id):
    config = agent['configuration']
    if config['tasks'] != ['products']:
        bad('La activación solo admite Productos nuevos. Las demás tareas todavía no son compatibles.', 422)
    if len(config['scopes']) != 1 or len(config['categories']) != 1:
        bad('La activación requiere un único ámbito y una única categoría.', 422)
    labels = {x['id']: x['name'] for x in config.get('categoryLabels', [])}
    query = labels.get(config['categories'][0])
    if not query or len(query) > 500:
        bad('Volvé a guardar la categoría del agente antes de activarlo.', 422)
    parameters = dict(query=query, country=config['country'], city=config['city'],
        scope_id=config['scopes'][0], category_id=config['categories'][0], language=config['language'])
    capabilities = ['dpia.amazon.search']
    instructions = 'Buscar productos de la categoría configurada.'
    tool_parameters = {'dpia.amazon.search': parameters}
    context = config.get('query_context')
    if context:
        # Monetary purchase limits belong to analysis, never to the scraper request.
        instructions = json.dumps({'country': config['country'], 'city': config['city'],
            'scope_id': config['scopes'][0], 'category_id': config['categories'][0],
            'language': config['language'], **context}, ensure_ascii=False)
        if len(instructions) > 8000:
            bad('El pedido completo supera el límite de instrucciones de Agents.', 422)
        if context['postal_id']:
            parameters['postal_id'] = context['postal_id']
        capabilities.append('openai.analysis')
        tool_parameters['openai.analysis'] = {'instructions':
            'Aplicá el pedido y el presupuesto de compra de las instrucciones del agente al analizar los resultados. '
            'Diferenciá precios de compra y venta. No inventes precios ni fuentes.'}
    return dict(owner_id=user_id, source_agent_id=agent['id'], source_revision=agent['revision'],
        agent=dict(name='Mi agente', instructions=instructions,
            capabilities=capabilities, timezone=config['timezone'],
            tool_parameters=tool_parameters,
            limits=dict(max_tool_calls=len(capabilities), max_output_tokens=2000, max_duration_seconds=300, max_corrections=0)),
        schedule=dict(timezone=config['timezone'], frequency='DAILY' if config['frequency']=='daily' else 'WEEKLY',
            weekdays=list(range(1,8)) if config['frequency']=='daily' else sorted(d or 7 for d in config['days']),
            execution_time=config['time'], delivery_time=config['time'], dst_policy='REJECT_AMBIGUOUS_OR_NONEXISTENT'),
        preferences={k: config[k] for k in ('points', 'period', 'notifications')})


def provision(payload):
    try:
        payload = {**payload, 'agent': normalize_task_payload(payload['agent'])}
    except ValueError as exc:
        bad(str(exc), 422)
    base = current_app.config.get('AGENTS_INTERNAL_URL', '').rstrip('/')
    secret = current_app.config.get('PWA_ACTIVATION_SECRET', '')
    parsed = urlsplit(base)
    if (not secret or parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        bad('La conexión interna del agente no está configurada.', 503)
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    stamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw, hashlib.sha256).hexdigest()
    try:
        response = requests.post(base+PATH, data=raw, headers={'Content-Type': 'application/json',
            'X-DPIA-Timestamp': stamp, 'X-DPIA-Signature': signature}, timeout=(3.05, 15), allow_redirects=False)
        if response.status_code != 200:
            bad('El servicio no confirmó la activación. Revisá la configuración o reintentá.', 502)
        result = response.json()
        remote = result['agent']
        from uuid import UUID
        if (result['api_version'] != 'agents.v1' or type(result['owner_id']) is not int
                or result['owner_id'] != payload['owner_id'] or result['source_agent_id'] != payload['source_agent_id']
                or result['source_revision'] != payload['source_revision'] or result['execution_enabled'] is not False
                or remote['configuration_state'] != 'ENABLED' or str(UUID(remote['id'])) != remote['id']
                or type(remote['revision']) is not int or remote['revision'] < 1):
            raise ValueError()
        return {'id': remote['id'], 'revision': remote['revision']}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        bad('No se confirmó la activación del agente. Reintentá; no se creará un duplicado.', 502)


def synchronize_task(user_id, agent_id, task_id, schedule=None):
    """Use the existing signed provisioning endpoint after the local task commits."""
    payload=dict(operation='sync_task_schedule' if schedule is None else 'update_task_schedule',owner_id=user_id,source_agent_id=agent_id,task_id=task_id)
    if schedule is not None:payload['schedule']=schedule
    base=current_app.config.get('AGENTS_INTERNAL_URL','').rstrip('/')
    secret=current_app.config.get('PWA_ACTIVATION_SECRET','')
    parsed=urlsplit(base)
    if (not secret or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        bad('La conexión interna del agente no está configurada.',503)
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    stamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    try:
        response=requests.post(base+PATH,data=raw,headers={'Content-Type':'application/json',
            'X-DPIA-Timestamp':stamp,'X-DPIA-Signature':signature},timeout=(3.05,15),allow_redirects=False)
        data=response.json()
        if response.status_code!=200:
            code=data.get('error',{});code=code.get('code') if isinstance(code,dict) else code
            message={'revision_conflict':'La programación cambió. Volvé a cargar la tarea.',
                'execution_time_in_past':'Elegí una fecha y hora futuras.',
                'task_paused':'Activá la tarea antes de habilitar su programación.',
                'invalid_contract':'Revisá la fecha, hora, frecuencia y días seleccionados.'}.get(code,'No se confirmó la programación de la tarea. Reintentá.')
            bad(message,response.status_code if response.status_code in (400,409,422) else 502)
        if (data['api_version']!='agents.v1' or type(data['owner_id']) is not int or data['owner_id']!=user_id
                or type(data['source_agent_id']) is not int or data['source_agent_id']!=agent_id
                or type(data['task_id']) is not int or data['task_id']!=task_id or data['execution_enabled'] is not False
                or data['schedule']['legacy_task_id']!=task_id):raise ValueError()
        return data['schedule']
    except (requests.RequestException,ValueError,KeyError,TypeError):
        bad('No se confirmó la programación de la tarea. Reintentá.',502)


def task_sources(user_id):
    """Read the live catalog through the existing signed Agents service boundary."""
    payload={'operation':'task_sources','owner_id':user_id}
    base=current_app.config.get('AGENTS_INTERNAL_URL','').rstrip('/')
    secret=current_app.config.get('PWA_ACTIVATION_SECRET','')
    parsed=urlsplit(base)
    if (not secret or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        bad('La conexión interna del agente no está configurada.',503)
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    stamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    try:
        response=requests.post(base+PATH,data=raw,headers={'Content-Type':'application/json',
            'X-DPIA-Timestamp':stamp,'X-DPIA-Signature':signature},timeout=(3.05,15),allow_redirects=False)
        data=response.json()
        if response.status_code!=200 or data.get('api_version')!='agents.v1' or data.get('owner_id')!=user_id:
            raise ValueError()
        items=data['items']
        if not isinstance(items,list) or any(not isinstance(item,dict) or not all(isinstance(item.get(key),str) for key in ('id','name','kind')) for item in items):raise ValueError()
        return [{'id':item['id'],'name':item['name'],'kind':item['kind']} for item in items]
    except (requests.RequestException,ValueError,KeyError,TypeError):
        bad('No se pudieron cargar las conexiones disponibles de Agents. Reintentá.',502)


def schedule_immediate_task(user_id, agent_id, task_id, request_id, *, existing=False):
    payload=dict(operation='run_existing_task_now' if existing else 'schedule_task_now',owner_id=user_id,source_agent_id=agent_id,task_id=task_id,request_id=request_id)
    base=current_app.config.get('AGENTS_INTERNAL_URL','').rstrip('/')
    secret=current_app.config.get('PWA_ACTIVATION_SECRET','')
    parsed=urlsplit(base)
    if (not secret or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        bad('La conexión interna del agente no está configurada. La tarea quedó guardada; podés reintentar.',503)
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode();stamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    try:
        response=requests.post(base+PATH,data=raw,headers={'Content-Type':'application/json',
            'X-DPIA-Timestamp':stamp,'X-DPIA-Signature':signature},timeout=(3.05,20),allow_redirects=False)
        data=response.json()
        if response.status_code!=200:
            code=data.get('error',{});code=code.get('code') if isinstance(code,dict) else code
            message={'agent_paused':'La tarea quedó guardada. Reanudá el agente y reintentá este envío.',
                     'agent_disabled':'La tarea quedó guardada. Habilitá el agente y reintentá este envío.',
                     'selected_sources_unavailable':'La tarea quedó guardada, pero una conexión elegida no está disponible.',
                     'VIDEO_EXECUTION_ALREADY_PENDING':'Hay una ejecución activa o una corrida programada próxima. Esperá a que termine.'}.get(code,'No se confirmó la ejecución. La tarea quedó guardada; reintentá el mismo envío.')
            bad(message,409 if response.status_code==409 else 502)
        if (data.get('api_version')!='agents.v1' or data.get('owner_id')!=user_id
                or data.get('source_agent_id')!=agent_id or data.get('task_id')!=task_id
                or data.get('request_id')!=request_id or data['schedule']['legacy_task_id']!=task_id
                or data['agent']['configuration_state']!='ENABLED'):
            raise ValueError()
        return data
    except (requests.RequestException,ValueError,KeyError,TypeError):
        bad('No se confirmó la ejecución. La tarea quedó guardada; reintentá el mismo envío para evitar duplicados.',502)


def video_quote(user_id, agent_id, task_id, configuration):
    """Read-only quote using the existing authenticated Agents boundary."""
    payload=dict(operation='video_quote',owner_id=user_id,source_agent_id=agent_id,task_id=task_id,**configuration)
    base=current_app.config.get('AGENTS_INTERNAL_URL','').rstrip('/')
    secret=current_app.config.get('PWA_ACTIVATION_SECRET','')
    parsed=urlsplit(base)
    if not secret or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        bad('La conexión con Agents no está configurada.',503)
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    stamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    from decimal import Decimal, InvalidOperation
    try:
        response=requests.post(base+PATH,data=raw,headers={'Content-Type':'application/json','X-DPIA-Timestamp':stamp,'X-DPIA-Signature':signature},timeout=(3.05,30),allow_redirects=False)
        data=response.json()
        if response.status_code!=200:
            bad('No hay una cotización disponible.',409 if response.status_code in (400,409,422) else 502)
        amount=Decimal(data['amount'])
        if data['currency']!='USD' or not amount.is_finite() or amount<=0:
            raise ValueError()
        rate=Decimal(data['usd_per_credit'])
        revision=data['policy_revision']
        if not rate.is_finite() or rate<=0 or type(revision) is not int or revision<1:
            raise ValueError()
        return {'amount':str(amount),'currency':'USD','provisional':data['provisional'],'valid_until':data['valid_until'],
                'usd_per_credit':str(rate),'policy_revision':revision}
    except (requests.RequestException,ValueError,KeyError,TypeError,InvalidOperation):
        bad('No se pudo consultar la cotización.',502)
