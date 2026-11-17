"""OpenAI interpretation only; B2B retains authority over state transitions."""
import json
import requests
import logging
import os

logger = logging.getLogger(__name__)

SCHEMA = {
    'type':'object','additionalProperties':False,
    'properties':{
        'intent':{'type':'string'},'objective':{'type':'string'},
        'sufficient':{'type':'boolean'},'question':{'type':'string'},
        'summary':{'type':'string'},'task_title':{'type':'string'},'search_type':{'type':'string'},'search_market':{'type':'string'},'product_category':{'type':'string'},'budget':{'type':'string'},'expected_result':{'type':'string'},'missing_required':{'type':'array','items':{'type':'string'}}},
    'required':['intent','objective','sufficient','question','summary','task_title','search_type','search_market','product_category','budget','expected_result','missing_required']
}

INSTRUCTIONS = '''Sos el intérprete de intenciones de DPIA. Devolvé SOLO el JSON del esquema.
El usuario puede estar empezando a revender (start) o buscando empleo (jobs).
La selección de situación y acción ya expresa parte de la intención; NO preguntes lo ya conocido.
Preguntá una sola cosa cuando sin ella no se pueda elegir una búsqueda útil.
Para jobs, un puesto, oficio, habilidad o sector es suficiente; no exijas salario, país ni modalidad.
Para start+explore/novel/local se puede investigar de forma amplia sin producto ni presupuesto.
No confundas ubicación, ámbito y categoría de PUBLICACIÓN con filtros de BÚSQUEDA.
No inventes restricciones ni proveedores ni vacantes. La ubicación de la interfaz NO es filtro de búsqueda.
Si hay una corrección posterior, prevalece sobre la información anterior.
No afirmes que el usuario confirmó. La confirmación la controla el servidor.
El objetivo es una instrucción breve y ejecutable. Si falta algo imprescindible, sufficient=false y question es una pregunta natural.
Si sufficient=true, question debe ser cadena vacía.
Devolvé además una vista estructurada de la tarea: task_title breve, search_type, search_market, product_category, budget, expected_result y missing_required (lista de campos INDISPENSABLES que impiden ejecutar).
Los campos desconocidos deben ser cadenas vacías. NO copies el prompt entero a esos campos. NO conviertas el país/ciudad de la interfaz en search_market; solamente completalo si el usuario lo indicó explícitamente como mercado de investigación. NO conviertas presupuestos sugeridos por el sistema en presupuesto confirmado por el usuario. Categoría y presupuesto suelen ser opcionales. missing_required debe estar vacío si sufficient=true; si falta algo indispensable, incluí su nombre concreto. task_title debe describir la tarea, no ser una copia del prompt.
'''

class IntentProviderError(Exception):
    pass


def interpret(payload, config):
    # Reuse the application configuration; do not create a second OpenAI client or key.
    # Flask config normally imports config.py, but some deployments inject credentials
    # through the process environment after configuration initialization.
    key=(config.get('OPENAI_API_KEY') or os.environ.get('OPENAI_API_KEY') or '').strip()
    if not key:
        logger.error('DPIA intent resolver: OPENAI_API_KEY absent from Flask config (existing provider configuration)')
        raise IntentProviderError('openai_not_configured')
    messages=payload.get('messages')
    if not isinstance(messages,list) or len(messages)>24:
        raise ValueError('invalid_messages')
    for m in messages:
        if not isinstance(m,dict) or m.get('role') not in ('user','assistant') or not isinstance(m.get('content'),str) or len(m['content'])>3000:
            raise ValueError('invalid_messages')
    data={'situation':payload['situation'],'action':payload.get('action','search'),
          'messages':messages,'initial_message':str(payload.get('message') or '')[:3000],
          'answers':payload.get('answers') or []}
    try:
        with requests.post('https://api.openai.com/v1/responses',
            headers={'Authorization':'Bearer '+key},
            json={'model':config.get('OPENAI_MODEL') or os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini','store':False,
                  'instructions':INSTRUCTIONS,
                  'input':json.dumps(data,ensure_ascii=False),
                  'max_output_tokens':650,
                  'text':{'format':{'type':'json_schema','name':'dpia_intent_v1','strict':True,'schema':SCHEMA}}},
            timeout=(3.05,25),allow_redirects=False) as response:
            if response.status_code!=200:
                # Keep provider diagnostics server-side; never log the API key or request payload.
                logger.error('DPIA intent resolver: OpenAI HTTP %s; request_id=%s', response.status_code, response.headers.get('x-request-id', 'unknown'))
                if response.status_code == 401:
                    raise IntentProviderError('openai_auth_failed')
                if response.status_code == 429:
                    raise IntentProviderError('openai_rate_limited')
                raise IntentProviderError('openai_unavailable')
            body=response.json()
        if body.get('status')!='completed':
            raise IntentProviderError('openai_incomplete')
        outputs=[part.get('text') for output in body.get('output',[]) if output.get('type')=='message'
                 for part in output.get('content',[]) if part.get('type')=='output_text']
        if len(outputs)!=1:raise IntentProviderError('openai_invalid_response')
        result=json.loads(outputs[0]);
        if not isinstance(result,dict) or set(result)!=set(SCHEMA['required']):raise ValueError()
        if any(not isinstance(result[k],str) for k in ('intent','objective','question','summary','task_title','search_type','search_market','product_category','budget','expected_result')) or type(result['sufficient']) is not bool:raise ValueError()
        if any(len(result[k])>2000 for k in ('intent','objective','question','summary','task_title','search_type','search_market','product_category','budget','expected_result')):raise ValueError()
        if not isinstance(result['missing_required'],list) or any(not isinstance(v,str) or len(v)>100 for v in result['missing_required']):raise ValueError()
        return result
    except requests.Timeout as exc:
        logger.warning('DPIA intent resolver: OpenAI request timed out')
        raise IntentProviderError('openai_timeout') from exc
    except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
        logger.error('DPIA intent resolver: provider transport or parsing error (%s)', type(exc).__name__)
        raise IntentProviderError('openai_invalid_response') from exc
