"""Dispatch validated results to existing DPIA endpoints; internal sources stay local."""
import requests
import re
from sqlalchemy import or_, func
from model.publicaciones.publicaciones import Publicacion
from services.dpia_client import DPIAClient
from services.query_preparation import PreparationError
from services.query_sources import EXTERNAL, search_terms
from services.result_generation import sheet_rows

COUNTRY_KEYS={'Argentina':'argentina','Italia':'italia','España':'espana','Polonia':'polonia','México':'mexico','Uruguay':'uruguay'}


def internal_results(source,prepared,store):
    if source=='historial':return store.history(prepared['context']['usuario'],prepared)
    from services.local_publications import publications_for_city
    ctx=prepared['context'];cat=prepared['ids']['categoria_id'];terms=search_terms(prepared['user_message'])
    if source=='local':
        # Same existing postal scope, with keyword filtering before pagination.
        rows,_=publications_for_city(ctx['pais'],ctx['ciudad'],category_id=cat,terms=terms)
        return rows
    query=Publicacion.query.filter(func.lower(func.trim(Publicacion.estado))=='activo',Publicacion.categoria_id==cat)
    if terms:query=query.filter(or_(*(or_(Publicacion.titulo.ilike('%'+t+'%'),Publicacion.descripcion.ilike('%'+t+'%')) for t in terms)))
    rows=query.order_by(Publicacion.fecha_creacion.desc(),Publicacion.id.desc()).limit(24).all()
    return [dict(id=row.id,titulo=row.titulo,descripcion=row.descripcion,imagen=row.imagen,precio=row.precio,moneda=row.moneda) for row in rows]


def dispatch_external(source,result,config):
    if source not in EXTERNAL:raise PreparationError('Este origen no permite scraping externo.')
    key=config.get('DPIA_SCRAPING_KEY') or config.get('SCRAPEADOR_SERVICE_KEY','')
    if not key:return {'status':'not_configured','error':'Falta la clave del servicio de scraping.'}
    headers={'Authorization':f'Bearer {key}'}
    try:
        with requests.get(DPIAClient.BASE_URL+'/marketplaces',headers=headers,timeout=(3.05,10),allow_redirects=False) as response:
            if response.status_code!=200:return {'status':'failed','error':'No se pudieron verificar los marketplaces disponibles.'}
            markets=response.json().get('datos',{})
        country=COUNTRY_KEYS.get(result['context']['pais'])
        if country not in markets.get(source,{}).get('domains',{}):
            return {'status':'unsupported_country','error':'El marketplace no admite el país seleccionado.'}
        rows=sheet_rows(result)
        # Preserve the complete verified context; only the marketplace country changes its wire format.
        for row in rows:row['País']=country
        with requests.post(DPIAClient.BASE_URL+'/scraping/'+source,headers=headers,
                           json={'pais_defecto':country,'registros':rows},timeout=(3.05,180),allow_redirects=False) as response:
            if response.status_code!=200:
                return {'status':'failed','error':'El servicio rechazó el scraping. Verificá el permiso scraper:write.'}
            data=response.json()
        if not data.get('success') or not isinstance(data.get('datos'),list):
            return {'status':'failed','error':'El servicio no devolvió resultados válidos.'}
        def clean(value):
            if isinstance(value,dict):return {k:('El proveedor no completó esta búsqueda.' if k=='error' and v else clean(v)) for k,v in value.items() if k.lower() not in ('token','api_key','authorization','password','access_token','secret')}
            if isinstance(value,list):return [clean(v) for v in value]
            if isinstance(value,str):return re.sub(r'(?i)([?&](?:token|api_key|access_token)=)[^&\s]+',r'\1[REDACTADO]',value.replace(key,'[REDACTADO]'))
            return value
        return {'status':'complete','data':clean(data['datos'])}
    except requests.Timeout:
        return {'status':'unknown','error':'El servicio tardó demasiado. El trabajo puede seguir activo; no se reenviará automáticamente.'}
    except (requests.RequestException,ValueError,TypeError,AttributeError):
        return {'status':'failed','error':'No se pudo completar la conexión con el servicio de scraping.'}


def execute_sources(prepared,result,config,store):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.exc import SQLAlchemyError
    from utils.db import db
    outcomes={}
    if result['needs_clarification']:
        return {source:{'status':'clarification_required'} for source in prepared['sources']}
    retrieval=prepared
    if prepared.get('attachments') and result.get('query',{}).get('normalized_intent'):
        retrieval={**prepared,'user_message':result['query']['normalized_intent']}
    for source in prepared['sources']:
        if source not in EXTERNAL:
            try:outcomes[source]={'status':'complete','data':internal_results(source,retrieval,store)}
            except SQLAlchemyError:
                db.session.rollback();outcomes[source]={'status':'failed','error':'No se pudieron consultar las publicaciones.'}
    selected=[source for source in prepared['sources'] if source in EXTERNAL]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={source:pool.submit(dispatch_external,source,result,dict(config)) for source in selected}
        for source,future in futures.items():outcomes[source]=future.result()
    return outcomes
