"""Image preparation from owned persisted products, using DPIA's ASIN endpoint.

Filter semantics match filtro_publicacion.validar_filtros_scraper and diagnostics
in dpia-popup-service. No generated prices, margins or media URLs.
"""
import json
import math
import re
from urllib.parse import urlsplit
import requests
from services.dpia_client import DPIAClient
from services.query_execution import normalize_products, safe_product_url
from services.query_preparation import PreparationError

DEFAULTS = dict(precio_minimo=0, precio_maximo=None, rating_minimo=4.4, resenas_minimas=50)


def validate_filters(value):
    if not isinstance(value, dict) or set(value)-set(DEFAULTS):
        raise PreparationError('Filtros no reconocidos.')
    result = {**DEFAULTS, **value}
    for key, number in result.items():
        if key=='precio_maximo' and number is None:continue
        if type(number) not in (int,float) or not math.isfinite(number) or number<0:
            raise PreparationError('Los filtros deben ser números finitos no negativos.')
    if not 0<result['rating_minimo']<=5 or type(result['resenas_minimas']) is not int or result['resenas_minimas']<1:
        raise PreparationError('Revisá el rating mínimo y la cantidad de reseñas.')
    if result['precio_maximo'] is not None and result['precio_maximo']<result['precio_minimo']:
        raise PreparationError('El precio máximo no puede ser menor al mínimo.')
    return result


def number(value):
    if value is None or value=='':return None
    if type(value) in (int,float):return float(value) if math.isfinite(value) else None
    match=re.search(r'(\d+[.,]?\d*)',str(value))
    parsed=float(match[1].replace(',','.')) if match else None
    return parsed if parsed is not None and math.isfinite(parsed) else None


def diagnostics(item, filters):
    price,rating=number(item.get('precio')),number(item.get('rating'))
    match=re.search(r'(\d[\d.,]*)',str(item.get('reviews') or ''))
    reviews=int(match[1].replace('.','').replace(',','')) if match else 0
    checks={'precio':bool(price and price>0 and price>=filters['precio_minimo'] and
              (filters['precio_maximo'] is None or price<=filters['precio_maximo'])),
            'rating':rating is None or rating>=filters['rating_minimo'],
            'resenas':rating is None or reviews>=filters['resenas_minimas']}
    return {'eligible':all(checks.values()),'checks':checks,'price':price,'rating':rating,
            'reviews':reviews,'rating_missing':rating is None}


def raw_product(operation, index):
    outcome=json.loads(operation['outcome']) if operation.get('outcome') else {}
    products=outcome.get('products') or []
    if type(index) is not int or not 0<=index<len(products):
        raise PreparationError('Producto no encontrado.',404)
    selected=products[index]
    for group in outcome.get('data') or []:
        if not isinstance(group,dict):continue
        for item in group.get('items') or []:
            normalized=normalize_products([{'items':[item]}],operation['source'])
            if normalized and normalized[0]==selected:
                return item
    raise PreparationError('No se pudo verificar el producto original.',409)


def prepare_images(quota, operation_id, user_id, index, filters, config):
    operation=quota.operation(operation_id,user_id)
    if not operation:raise PreparationError('Operación no encontrada.',404)
    if operation['source']!='amazon':raise PreparationError('La galería por ASIN está disponible para Amazon.')
    item=raw_product(operation,index)
    filters=validate_filters(filters);diagnosis=diagnostics(item,filters)
    if not diagnosis['eligible']:
        return {'success':True,'status':'filtered','images':[],'diagnostics':diagnosis,'filters':filters}
    asin=item.get('asin')
    try:host=(urlsplit(item.get('url') or '').hostname or '').lower()
    except (ValueError,AttributeError,TypeError):raise PreparationError('La URL original del producto no es válida.') from None
    domains=('com','ca','fr','it','de','es','pl')
    domain=next((d for d in domains if host in ('amazon.'+d,'www.amazon.'+d)),None)
    if not isinstance(asin,str) or not re.fullmatch(r'[A-Za-z0-9]{10}',asin) or not domain:
        raise PreparationError('El producto no tiene un ASIN y dominio Amazon compatibles.')
    # Reading cached galleries does not require enabling providers.
    old=json.loads(operation['outcome']).get('image_stages',{}).get(str(index),{})
    if old.get('status')=='complete':
        return {'success':True,**{k:v for k,v in old.items() if k!='token'},'diagnostics':diagnosis,'filters':filters}
    if not config.get('LIVE_PROVIDER_CALLS_ENABLED',False):
        raise PreparationError('Las llamadas reales están deshabilitadas.',503)
    key=config.get('SCRAPEADOR_SERVICE_KEY','')
    if not key:raise PreparationError('Falta SCRAPEADOR_SERVICE_KEY.',503)
    headers={'Authorization':'Bearer '+key}
    try:
        with requests.get(DPIAClient.BASE_URL+'/auth/check',params={'permiso':'scraper:write'},
                          headers=headers,timeout=(3.05,10),allow_redirects=False) as response:
            if response.status_code!=200 or response.json().get('success') is not True:
                raise PreparationError('No se pudo autorizar la preparación de imágenes.',403)
    except (requests.RequestException,ValueError):
        raise PreparationError('No se pudo verificar el permiso de imágenes.',502) from None
    claim=quota.image_stage(operation_id,user_id,index)
    if claim.get('status')=='complete':
        return {'success':True,**{k:v for k,v in claim.items() if k!='token'},'diagnostics':diagnosis,'filters':filters}
    token=claim['token']
    def save(stage):
        stage={**stage,'filters':filters,'diagnostics':diagnosis}
        quota.image_stage(operation_id,user_id,index,token=token,stage=stage)
        return {'success':True,**stage,'diagnostics':diagnosis,'filters':filters}
    try:
        with requests.post(DPIAClient.BASE_URL+'/imagenes/asin',headers=headers,
            json={'asin':asin,'dominio':domain},timeout=(3.05,180),allow_redirects=False) as response:
            if response.status_code in (400,401,403,404,415):
                return save({'status':'failed','images':[],'error':'La API rechazó la preparación de imágenes.'})
            if response.status_code!=200:
                return save({'status':'pending','images':[],'error':'La API no confirmó el resultado. No se reenviará automáticamente.'})
            data=response.json()
        if not isinstance(data,dict) or data.get('success') is not True or not isinstance(data.get('imagenes'),list):
            return save({'status':'pending','images':[],'error':'Respuesta de imágenes sin confirmación.'})
        photos=[]
        for value in [item.get('imagen'),*data['imagenes']]:
            if isinstance(value,dict):value=value.get('imageUrl')
            url=safe_product_url(value)
            if url and not urlsplit(url).password and url not in photos:photos.append(url)
        return save({'status':'complete','images':photos[:6]})
    except requests.ConnectTimeout:
        return save({'status':'failed','images':[],'error':'No se pudo conectar con el servicio de imágenes.'})
    except (requests.RequestException,ValueError):
        return save({'status':'pending','images':[],'error':'Se perdió la confirmación de las imágenes. No se reenviará automáticamente.'})
