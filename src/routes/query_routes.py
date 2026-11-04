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
    from pathlib import Path
    import re
    import sqlite3
    import uuid
    from services.query_sources import EXTERNAL
    from services.query_execution import execute_sources
    from services.query_store import QueryStore
    from services.query_preparation import result_template
    store=None;reserved=False;request_id=None
    try:
        body=request.get_json(silent=True)
        prepared=prepare_context(body,session['user_id'])
        request_id=body.get('request_id') or str(uuid.uuid4())
        if not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}',request_id):
            raise PreparationError('Identificador de consulta inválido.')
        store=QueryStore(current_app.config.get('QUERY_STORE_PATH',str(Path(current_app.instance_path)/'queries.sqlite3')))
        cached=store.reserve(request_id,session['user_id'],body)
        if cached is not None:return jsonify(cached)
        reserved=True
        external=any(source in EXTERNAL for source in prepared['sources'])
        result=generate(prepared,current_app.config) if external or prepared.get('attachments') else result_template(prepared)
        outcomes=execute_sources(prepared,result,current_app.config,store)
        payload=dict(success=True,result=result,rows=sheet_rows(result),sources=outcomes,
                     request_id=request_id,internal_only=not external,context_ids=prepared['ids'])
        store.finish(request_id,payload)
        return jsonify(payload)
    except PreparationError as exc:
        if reserved:store.fail(request_id)
        return jsonify(success=False,error=str(exc)),exc.status
    except CatalogError:
        if reserved:store.fail(request_id)
        return jsonify(success=False,error='No se pudo verificar el catálogo.'),502
    except SQLAlchemyError:
        db.session.rollback()
        if reserved:store.fail(request_id)
        return jsonify(success=False,error='No se pudo verificar la consulta.'),503
    except (OSError,sqlite3.Error):
        if reserved:store.fail(request_id)
        return jsonify(success=False,error='No se pudo guardar el historial de la consulta.'),503
