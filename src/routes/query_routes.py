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
                       generation_available=bool(current_app.config.get('OPENAI_API_KEY')))
    except PreparationError as exc:
        return jsonify(success=False, error=str(exc)), exc.status
    except CatalogError:
        return jsonify(success=False, error='No se pudo verificar el catálogo. Reintentá.'), 502
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(success=False, error='No se pudo verificar el contexto de la consulta.'), 503


@query_bp.post('/generar')
def generate_query():
    if type(session.get('user_id')) is not int:
        return jsonify(success=False,error='Iniciá sesión para generar la consulta.'),401
    try:
        prepared=prepare_context(request.get_json(silent=True),session['user_id'])
        result=generate(prepared,current_app.config)
        return jsonify(success=True,result=result,rows=sheet_rows(result))
    except PreparationError as exc:
        return jsonify(success=False,error=str(exc)),exc.status
    except CatalogError:
        return jsonify(success=False,error='No se pudo verificar el catálogo.'),502
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(success=False,error='No se pudo verificar la consulta.'),503
