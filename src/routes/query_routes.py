"""Prepare a verified query; generation transport requires an API contract."""
from flask import Blueprint, jsonify, request, session, current_app
from sqlalchemy.exc import SQLAlchemyError
from services.dpia_client import CatalogError
from services.query_preparation import PreparationError, prepare_context, public_summary, build_private_prompt
from utils.db import db
from services.result_generation import generate, sheet_rows

query_bp = Blueprint('queries', __name__, url_prefix='/api/consultas')


@query_bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@query_bp.post('/preparar')
def prepare():
    if type(session.get('user_id')) is not int:
        return jsonify(success=False, error='Iniciá sesión para preparar la consulta.'), 401
    try:
        prepared = prepare_context(request.get_json(silent=True), session['user_id'])
        # Construct only on the server. It is neither returned nor stored in a session cookie.
        build_private_prompt(prepared)
        return jsonify(success=True, summary=public_summary(prepared), context=prepared['context'],
                       generation_available=False,external_execution_available=False,history_available=False)
    except PreparationError as exc:
        return jsonify(success=False, error=str(exc)), exc.status
    except CatalogError:
        return jsonify(success=False, error='No se pudo verificar el catálogo. Reintentá.'), 502
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(success=False, error='No se pudo verificar el contexto de la consulta.'), 503


def persistence_unavailable():
    return jsonify(success=False,code='persistence_not_configured',payments_enabled=False,
                   error='El almacenamiento del contador y del historial no está configurado.'),503


@query_bp.get('/creditos')
def scraping_credits():
    if type(session.get('user_id')) is not int:
        return jsonify(success=False,error='Iniciá sesión para ver tus ejecuciones.'),401
    quota=current_app.extensions.get('scraping_quota')
    if quota is None:return persistence_unavailable()
    try:
        return jsonify(success=True,credits=quota.credits(session['user_id']),
                       test_credits_enabled=test_credits_enabled(),payments_enabled=False)
    except PreparationError as exc:
        return jsonify(success=False,error=str(exc)),exc.status
    except SQLAlchemyError:
        return persistence_unavailable()


def test_credits_enabled():
    return bool(current_app.debug and current_app.config.get('ENABLE_TEST_SCRAPING_CREDITS',False))


@query_bp.post('/creditos/prueba')
def grant_test_credits():
    if type(session.get('user_id')) is not int:
        return jsonify(success=False,error='Iniciá sesión.'),401
    if not test_credits_enabled():
        return jsonify(success=False,error='Recargas de prueba deshabilitadas.'),403
    # JSON + same-origin fetch header prevents cross-site form submissions.
    if not request.is_json or request.headers.get('X-DPIA-Test-Credits')!='1':
        return jsonify(success=False,error='Solicitud inválida.'),400
    quota=current_app.extensions.get('scraping_quota')
    if quota is None:return persistence_unavailable()
    try:
        quota.grant_test(session['user_id'])
        return jsonify(success=True,credits=quota.credits(session['user_id']))
    except PreparationError as exc:
        return jsonify(success=False,error=str(exc)),exc.status
    except SQLAlchemyError:
        return persistence_unavailable()


@query_bp.get('/operaciones/<operation_id>')
def query_operation(operation_id):
    if type(session.get('user_id')) is not int:
        return jsonify(success=False,error='Iniciá sesión.'),401
    quota=current_app.extensions.get('scraping_quota')
    if quota is None:return persistence_unavailable()
    try:
        operation=quota.operation(operation_id,session['user_id'])
        if not operation:return jsonify(success=False,error='Operación no encontrada.'),404
        import json
        from services.query_preparation import result_template
        outcome=json.loads(operation['outcome']) if operation.get('outcome') else {'status':'pending','products':[]}
        payload=dict(result=result_template(operation['prepared']),rows=[],request_id=operation_id,
                     sources={operation['source']:outcome})
        return jsonify(success=True,state=operation['state'],payload=payload)
    except PreparationError as exc:
        return jsonify(success=False,error=str(exc)),exc.status
    except SQLAlchemyError:
        return persistence_unavailable()


@query_bp.post('/generar')
def generate_query():
    if type(session.get('user_id')) is not int:
        return jsonify(success=False,error='Iniciá sesión para generar la consulta.'),401
    import re
    import uuid
    from services.query_sources import EXTERNAL
    from services.query_execution import execute_sources
    from services.query_preparation import result_template
    try:
        body=request.get_json(silent=True)
        prepared=prepare_context(body,session['user_id'])
        external=[source for source in prepared['sources'] if source in EXTERNAL]
        if len(external)>1:
            raise PreparationError('Elegí un solo marketplace por ejecución.')
        # No replacement persistence is installed implicitly. Paid execution stays
        # blocked until its server-side counter and replay protection are configured.
        if external or prepared.get('attachments'):
            return persistence_unavailable()
        request_id=body.get('request_id') or str(uuid.uuid4())
        if not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}',request_id):
            raise PreparationError('Identificador de consulta inválido.')
        result=result_template(prepared)
        outcomes=execute_sources(prepared,result,current_app.config)
        return jsonify(success=True,result=result,rows=sheet_rows(result),sources=outcomes,
                       request_id=request_id,internal_only=True,context_ids=prepared['ids'])
    except PreparationError as exc:
        return jsonify(success=False,error=str(exc)),exc.status
    except CatalogError:
        return jsonify(success=False,error='No se pudo verificar el catálogo.'),502
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(success=False,error='No se pudo verificar la consulta.'),503


@query_bp.post('/scraping-directo')
def direct_scraping():
    """Text-only scraping. Never invoke OpenAI or bypass durable reservations."""
    import uuid
    from services.query_sources import EXTERNAL
    from services.query_preparation import result_template
    from services.query_execution import execute_sources
    if type(session.get('user_id')) is not int:
        return jsonify(success=False,error='Iniciá sesión para buscar.'),401
    try:
        body=request.get_json(silent=True)
        if not isinstance(body,dict) or not isinstance(body.get('sources'),list):
            raise PreparationError('Elegí expresamente un marketplace para iniciar scraping.')
        if len(body['sources'])!=1 or body['sources'][0] not in EXTERNAL:
            raise PreparationError('Elegí un solo marketplace para scraping directo.')
        if body.get('attachments') or body.get('mode')!='buscar':
            raise PreparationError('El scraping directo admite únicamente texto de búsqueda.')
        try:
            operation_id=str(uuid.UUID(body.get('request_id','')))
        except (ValueError,TypeError,AttributeError):
            raise PreparationError('Identificador de consulta inválido.') from None
        prepared=prepare_context(body,session['user_id'])
        if len(prepared['user_message'])>500:
            raise PreparationError('La búsqueda directa admite hasta 500 caracteres.')
        # The durable repository must reserve atomically and enforce per-user
        # idempotency, payload identity and the six-execution limit. No memory store.
        quota=current_app.extensions.get('scraping_quota')
        if quota is None:
            return persistence_unavailable()
        quota.reserve_direct(operation_id,session['user_id'],prepared)
        result=result_template(prepared)
        for plan in result['scrape_plan']:
            plan['search_query']=prepared['user_message']
        outcomes=execute_sources(prepared,result,current_app.config,quota=quota,operation_id=operation_id)
        return jsonify(success=True,result=result,rows=[],sources=outcomes,
                       request_id=operation_id,flow='direct_scraping')
    except PreparationError as exc:
        if exc.status==402:
            return jsonify(success=False,code='insufficient_credit',error=str(exc),required=1,missing=1,
                           credits=current_app.extensions['scraping_quota'].credits(session['user_id'])),402
        return jsonify(success=False,error=str(exc)),exc.status
    except CatalogError:
        return jsonify(success=False,error='No se pudo verificar el catálogo.'),502
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(success=False,error='No se pudo verificar la consulta.'),503
