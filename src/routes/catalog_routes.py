"""Same-origin catalog endpoints; credentials remain on the server."""
from flask import Blueprint, current_app, jsonify, request

from services.dpia_client import CatalogError, CatalogFiltersError, DPIAClient, catalog_filters

catalog_bp = Blueprint("catalog", __name__, url_prefix="/api/catalogos")


@catalog_bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def load_catalog(name):
    try:
        params = catalog_filters(request.args, name)
        client = DPIAClient(
            current_app.config.get("SCRAPEADOR_SERVICE_KEY", ""),
            timeout=(current_app.config.get("DPIA_CONNECT_TIMEOUT", 3.05),
                     current_app.config.get("DPIA_READ_TIMEOUT", 10)),
        )
        return jsonify(client.catalog(name, params))
    except CatalogFiltersError:
        return jsonify(success=False, error="Filtros de catálogo inválidos."), 400
    except CatalogError as exc:
        return jsonify(success=False, error="No se pudo cargar el catálogo DPIA."), exc.status


@catalog_bp.get("/ambitos")
def ambitos():
    return load_catalog("ambitos")


@catalog_bp.get("/categorias")
def categorias():
    return load_catalog("categorias")
