"""Read active publications for all postal records of a selected city."""
from sqlalchemy import and_, func, or_
from model.codigoPostal import CodigoPostal
from model.publicaciones.publicaciones import Publicacion
from model.publicaciones.publicacionCodigoPostal import PublicacionCodigoPostal
from services.locations import postal_ids_for_city
from utils.db import db


def publications_for_city(country, city, offset=0):
    ids = postal_ids_for_city(country, city)
    if not ids:
        return [], False
    codes = db.session.query(CodigoPostal.codigoPostal).filter(CodigoPostal.id.in_(ids))
    local_relation = db.session.query(PublicacionCodigoPostal.id).filter(
        PublicacionCodigoPostal.publicacion_id == Publicacion.id,
        PublicacionCodigoPostal.codigoPostal_id.in_(ids),
    ).exists()
    any_relation = db.session.query(PublicacionCodigoPostal.id).filter(
        PublicacionCodigoPostal.publicacion_id == Publicacion.id,
    ).exists()
    # Legacy text is used only when there is no explicit postal association.
    local = or_(Publicacion.codigo_postal_id.in_(ids), local_relation, and_(
        Publicacion.codigo_postal_id.is_(None), ~any_relation,
        func.trim(Publicacion.codigoPostal).in_(codes),
    ))
    rows = Publicacion.query.filter(
        func.lower(func.trim(Publicacion.estado)) == 'activo', local,
    ).order_by(Publicacion.fecha_creacion.desc(), Publicacion.id.desc()).offset(offset).limit(25).all()
    return [dict(id=row.id, titulo=row.titulo, descripcion=row.descripcion,
                 imagen=row.imagen, precio=row.precio, moneda=row.moneda,
                 ciudad=city) for row in rows[:24]], len(rows) > 24
