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
    return persistence_unavailable()


@query_bp.get('/operaciones/<operation_id>')
def query_operation(operation_id):
    if type(session.get('user_id')) is not int:
        return jsonify(success=False,error='Iniciá sesión.'),401
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
