"""Read cities and postal IDs from the existing codigo_postal table."""
from sqlalchemy import func
from model.codigoPostal import CodigoPostal


def cities_for_country(country):
    rows = CodigoPostal.query.filter(
        func.lower(func.trim(CodigoPostal.pais)) == country.strip().lower(),
        CodigoPostal.ciudad.isnot(None),
    ).order_by(CodigoPostal.ciudad, CodigoPostal.id).all()
    cities = {}
    for row in rows:
        name = row.ciudad.strip()
        if not name:
            continue
        item = cities.setdefault(name.casefold(), {'nombre': name, 'codigo_postal_ids': []})
        item['codigo_postal_ids'].append(row.id)
    for item in cities.values():
        item['codigo_postal_ids'].sort()
    return sorted(cities.values(), key=lambda item: item['nombre'].casefold())


def postal_ids_for_city(country, city):
    return next((item['codigo_postal_ids'] for item in cities_for_country(country)
                 if item['nombre'].casefold() == city.strip().casefold()), [])
