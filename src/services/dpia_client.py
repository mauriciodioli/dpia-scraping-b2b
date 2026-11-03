"""Read-only DPIA catalog client. No network work happens on import."""
import re

import requests


class CatalogError(Exception):
    def __init__(self, status=502):
        super().__init__("No se pudo cargar el catálogo DPIA.")
        self.status = status


class CatalogFiltersError(ValueError):
    pass


def catalog_filters(args, catalog):
    allowed = {"idioma", "ambito_id", "codigo_postal_id"}
    if catalog == "categorias":
        allowed.add("categoria_id")
    if set(args) - allowed or any(len(args.getlist(k)) != 1 for k in args):
        raise CatalogFiltersError("Filtros de catálogo inválidos.")
    params = {}
    for key, value in args.items():
        if key == "idioma":
            value = value.strip()
            if len(value) > 20 or not re.fullmatch(r"[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*", value):
                raise CatalogFiltersError("Idioma inválido.")
            # The UI uses ISO 'en'; DPIA's existing catalog uses 'in'.
            params[key] = "in" if value == "en" else value
        else:
            if not re.fullmatch(r"[0-9]{1,10}", value) or not 0 < int(value) <= 2147483647:
                raise CatalogFiltersError("Identificador de catálogo inválido.")
            params[key] = int(value)
    return params


class DPIAClient:
    BASE_URL = "https://api.dpia.site/api/scraper/v1"

    def __init__(self, service_key, timeout=(3.05, 10)):
        self._service_key = service_key
        self.timeout = timeout

    def catalog(self, name, params):
        if name not in {"ambitos", "categorias"}:
            raise ValueError("Catálogo inválido.")
        if not self._service_key:
            raise CatalogError(503)
        try:
            with requests.get(
                f"{self.BASE_URL}/catalogos/{name}",
                headers={"Authorization": f"Bearer {self._service_key}"},
                params=params, timeout=self.timeout, allow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise CatalogError()
                payload = response.json()
        except requests.Timeout:
            raise CatalogError(504) from None
        except (requests.RequestException, ValueError):
            raise CatalogError() from None
        # Return only the verified contract, never arbitrary upstream fields/errors.
        if not isinstance(payload, dict) or payload.get("success") is not True or not isinstance(payload.get(name), list):
            raise CatalogError()
        fields = ("ambito_id", "nombre", "idioma") if name == "ambitos" else (
            "categoria_id", "categoria_general_id", "ambito_id", "ambito_ids", "nombre", "idioma")
        records = []
        for record in payload[name]:
            id_key = "ambito_id" if name == "ambitos" else "categoria_id"
            if (not isinstance(record, dict) or type(record.get(id_key)) is not int
                    or record[id_key] <= 0 or not isinstance(record.get("nombre"), str)
                    or not isinstance(record.get("idioma"), (str, type(None)))):
                raise CatalogError()
            if name == "categorias" and (
                not isinstance(record.get("ambito_ids"), list)
                or any(type(i) is not int for i in record["ambito_ids"])
                or any(record.get(k) is not None and type(record[k]) is not int
                       for k in ("ambito_id", "categoria_general_id"))
            ):
                raise CatalogError()
            clean = {key: record.get(key) for key in fields}
            for key in ("nombre", "idioma"):
                if isinstance(clean[key], str):
                    clean[key] = clean[key].replace(self._service_key, "[REDACTADO]")
            records.append(clean)
        return {"success": True, "total": len(records), name: records}
