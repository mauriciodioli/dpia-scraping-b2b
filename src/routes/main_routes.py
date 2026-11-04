"""Rutas de las páginas principales de la aplicación."""
from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return render_template("index.html")


@main_bp.get('/api/publicaciones/locales')
def local_publications():
    from flask import jsonify, request, current_app
    from sqlalchemy.exc import SQLAlchemyError
    from services.local_publications import publications_for_city
    from utils.db import db
    country = request.args.get('pais', '').strip()
    city = request.args.get('ciudad', '').strip()
    offset = request.args.get('offset', '0')
    if (not country or not city or len(country) > 100 or len(city) > 100
            or not offset.isdecimal() or len(offset) > 6):
        return jsonify(success=False, error='Elegí un país y una ciudad válidos.'), 400
    try:
        items, more = publications_for_city(country, city, int(offset))
        response = jsonify(success=True, publicaciones=items, has_more=more)
        response.headers['Cache-Control'] = 'no-store'
        return response
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Local publications query failed')
        return jsonify(success=False, error='No se pudieron cargar las publicaciones locales.'), 503
