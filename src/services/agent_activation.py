"""Translate only compatible saved configurations and confirm remote provisioning."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlsplit
import requests
from flask import current_app
from services.agent_configuration import bad

PATH = '/api/agents/v1/internal/pwa-activations'


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


def synchronize_task(user_id, agent_id, task_id):
    """Use the existing signed provisioning endpoint after the local task commits."""
    payload=dict(operation='sync_task_schedule',owner_id=user_id,source_agent_id=agent_id,task_id=task_id)
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
        if response.status_code!=200:bad('No se confirmó la programación de la tarea. Reintentá.',502)
        if (data['api_version']!='agents.v1' or type(data['owner_id']) is not int or data['owner_id']!=user_id
                or type(data['source_agent_id']) is not int or data['source_agent_id']!=agent_id
                or type(data['task_id']) is not int or data['task_id']!=task_id or data['execution_enabled'] is not False
                or data['schedule']['legacy_task_id']!=task_id):raise ValueError()
        return data['schedule']
    except (requests.RequestException,ValueError,KeyError,TypeError):
        bad('No se confirmó la programación de la tarea. Reintentá.',502)
