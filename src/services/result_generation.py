"""OpenAI JSON generation. No scraping, publishing, payments or Sheets writes."""
import json
import requests
from jsonschema import Draft202012Validator, ValidationError
from services.query_preparation import result_template, build_private_prompt, PreparationError


def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


TEXT={'type':'string'}
PRICE={'anyOf':[{'type':'number','minimum':0},{'type':'string','enum':['N/D']}]}


def result_schema(prepared):
    base=result_template(prepared)
    def infer(value):
        if isinstance(value,dict):return obj({k:infer(v) for k,v in value.items()})
        if isinstance(value,bool):return {'type':'boolean'}
        if isinstance(value,int):return {'type':'integer'}
        if isinstance(value,list):return {'type':'array','items':TEXT}
        return TEXT
    schema=infer(base)
    props=schema['properties']
    props['type']={'type':'string','enum':['results']}
    props['version']={'type':'string','enum':['dpia.results.v2']}
    props['context']=obj({key:{'type':'integer' if isinstance(value,int) else 'string','enum':[value]}
                          for key,value in prepared['context'].items()})
    props['constraints']['properties']['price']=obj({'min':PRICE,'max':PRICE,'currency':TEXT})
    props['constraints']['properties']['delivery_max_days']={'anyOf':[{'type':'integer','minimum':0},{'type':'string','enum':['N/D']}]}
    props['scrape_plan']={'type':'array','items':obj({'source':{'type':'string','enum':['amazon','ebay','aliexpress']},
        'country_domain':TEXT,'search_query':TEXT,'search_url':TEXT,'max_results':{'type':'integer','minimum':1,'maximum':20}})}
    fields={key:TEXT for key in ('producto','categoria','pais','fuente','motivo_tendencia','descripcion','fecha',
        'motivo_tendencia_extendido','ambito','codigoPostal','idioma','afiliado_link')}
    fields.update({'precios':obj({key:PRICE for key in ('amazon','ebay','aliexpress')}),
        'precio_venta_sugerido':PRICE,'margen_estimado':{'anyOf':[{'type':'number'},{'type':'string','enum':['N/D']}]},
        'busquedas':obj({key:TEXT for key in ('amazon','ebay','aliexpress')}),'usuario':{'type':'integer'},
        'estado':{'type':'string','enum':['CANDIDATO']},'botonCompra':{'type':'boolean','enum':[False]},
        'pagoOnline':{'type':'boolean','enum':[False]},'validado':{'type':'boolean','enum':[False]},
        'score_hint':{'type':'number','minimum':0,'maximum':100}})
    fields.update({key:TEXT for key in ('imagen','imagen2','imagen3','imagen4','imagen5','imagen6')})
    props['items']={'type':'array','items':obj(fields)}
    return schema


def validate_result(result, prepared):
    try:Draft202012Validator(result_schema(prepared)).validate(result)
    except ValidationError:raise PreparationError('La respuesta generada no cumple el formato DPIA.',502) from None
    if result['context']!=prepared['context']:
        raise PreparationError('La respuesta no corresponde a tu consulta.',502)
    if result['needs_clarification']:
        if result['items'] or not result['clarifying_question'].strip():
            raise PreparationError('La aclaración recibida no es válida.',502)
    elif not 5<=len(result['items'])<=10 or result['clarifying_question']:
        raise PreparationError('La cantidad de candidatos recibida no es válida.',502)
    seen=set()
    for item in result['items']:
        key=item['producto'].strip().casefold()
        if not key or key in seen:raise PreparationError('La respuesta contiene candidatos repetidos o vacíos.',502)
        seen.add(key)
        for field in ('ambito','categoria','pais','codigoPostal','usuario','fecha','idioma'):
            if item[field]!=prepared['context'][field]:raise PreparationError('El contexto del candidato no coincide.',502)
        if item['afiliado_link']:raise PreparationError('Los candidatos no pueden incluir afiliación sin verificar.',502)
    expected=result_template(prepared)['constraints']
    if (result['constraints']['shipping_to']!=expected['shipping_to'] or
            result['constraints']['price']['currency']!=expected['price']['currency']):
        raise PreparationError('El país o la moneda generados no coinciden.',502)
    # This text-only step has no verified marketplace evidence. Never display
    # model guesses as observed prices, margins, sources or product galleries.
    for item in result['items']:
        item['precios']={source:'N/D' for source in ('amazon','ebay','aliexpress')}
        item['precio_venta_sugerido']='N/D'
        item['margen_estimado']='N/D'
        item['fuente']='N/D'
        for key in ('imagen','imagen2','imagen3','imagen4','imagen5','imagen6'):item[key]='N/D'
    return result


def generate(prepared, config):
    key=config.get('OPENAI_API_KEY','')
    if not key:raise PreparationError('La generación de consultas no está configurada todavía.',503)
    schema=result_schema(prepared)
    prompt=build_private_prompt(prepared)+'\nIncluí imagen, imagen2, imagen3, imagen4, imagen5 e imagen6 como "N/D" si no están verificadas.'
    try:
        with requests.post('https://api.openai.com/v1/responses',headers={'Authorization':f'Bearer {key}'},
                json={'model':config.get('OPENAI_MODEL','gpt-4o-mini'),'store':False,'instructions':prompt,
                      'input':prepared['user_message'],'max_output_tokens':12000,
                      'text':{'format':{'type':'json_schema','name':'dpia_results_v2','strict':True,'schema':schema}}},
                timeout=(3.05,90),allow_redirects=False) as response:
            if response.status_code!=200:raise PreparationError('No se pudo generar la consulta. Reintentá más tarde.',502)
            payload=response.json()
        if payload.get('status')!='completed':raise PreparationError('La generación no se completó.',502)
        outputs=[part['text'] for output in payload.get('output',[]) if output.get('type')=='message'
                 for part in output.get('content',[]) if part.get('type')=='output_text']
        if len(outputs)!=1:raise PreparationError('No se recibió un resultado JSON completo.',502)
        def invalid_constant(value):
            raise ValueError('Non-JSON numeric value')
        result=json.loads(outputs[0],parse_constant=invalid_constant)
        serialized=json.dumps(result,allow_nan=False)
        for secret in (key,config.get('SCRAPEADOR_SERVICE_KEY','')):
            if secret and secret in serialized:raise PreparationError('La respuesta generada no es válida.',502)
        return validate_result(result,prepared)
    except requests.Timeout:raise PreparationError('La generación tardó demasiado. Reintentá.',504) from None
    except (requests.RequestException,ValueError,TypeError,KeyError,AttributeError):
        raise PreparationError('No se recibió una respuesta válida del generador.',502) from None


def sheet_rows(result):
    """Compatibility mapping only; does not write to Google Sheets."""
    rows=[]
    for item in result['items']:
        row={key:item[key] for key in ('descripcion','precio_venta_sugerido','margen_estimado','fecha',
             'motivo_tendencia_extendido','ambito','codigoPostal','usuario','estado','botonCompra','idioma',
             'pagoOnline','validado','afiliado_link','imagen','imagen2','imagen3','imagen4','imagen5','imagen6')}
        row.update({'Producto':item['producto'],'Categoría':item['categoria'],'País':item['pais'],
                    'Fuente':item['fuente'],'Motivo de tendencia':item['motivo_tendencia']})
        row.update({f'precio_{source}':item['precios'][source] for source in ('amazon','ebay','aliexpress')})
        row.update({f'búsqueda_{source}':item['busquedas'][source] for source in ('amazon','ebay','aliexpress')})
        rows.append(row)
    return rows
