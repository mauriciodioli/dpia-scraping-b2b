"""OpenAI interpretation only; B2B retains authority over state transitions."""
import json
import requests

SCHEMA = {
    'type':'object','additionalProperties':False,
    'properties':{
        'intent':{'type':'string'},'objective':{'type':'string'},
        'sufficient':{'type':'boolean'},'question':{'type':'string'},
        'summary':{'type':'string'}},
    'required':['intent','objective','sufficient','question','summary']
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
'''

class IntentProviderError(Exception):
    pass


def interpret(payload, config):
    key=config.get('OPENAI_API_KEY')
    if not key:
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
            json={'model':config.get('OPENAI_MODEL','gpt-4o-mini'),'store':False,
                  'instructions':INSTRUCTIONS,
                  'input':json.dumps(data,ensure_ascii=False),
                  'max_output_tokens':650,
                  'text':{'format':{'type':'json_schema','name':'dpia_intent_v1','strict':True,'schema':SCHEMA}}},
            timeout=(3.05,25),allow_redirects=False) as response:
            if response.status_code!=200:
                raise IntentProviderError('openai_unavailable')
            body=response.json()
        if body.get('status')!='completed':
            raise IntentProviderError('openai_incomplete')
        outputs=[part.get('text') for output in body.get('output',[]) if output.get('type')=='message'
                 for part in output.get('content',[]) if part.get('type')=='output_text']
        if len(outputs)!=1:raise IntentProviderError('openai_invalid_response')
        result=json.loads(outputs[0]);
        if not isinstance(result,dict) or set(result)!=set(SCHEMA['required']):raise ValueError()
        if any(not isinstance(result[k],str) for k in ('intent','objective','question','summary')) or type(result['sufficient']) is not bool:raise ValueError()
        if any(len(result[k])>2000 for k in ('intent','objective','question','summary')):raise ValueError()
        return result
    except requests.Timeout as exc:raise IntentProviderError('openai_timeout') from exc
    except (requests.RequestException,ValueError,TypeError,KeyError) as exc:raise IntentProviderError('openai_invalid_response') from exc
