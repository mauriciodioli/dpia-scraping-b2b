"""Transactional MySQL repository for the two manually provisioned PWA tables.

Separate metadata deliberately prevents db.create_all() from provisioning them.
"""
import hashlib
import json
from sqlalchemy import Table, Column, MetaData, Integer, String, Text, DateTime, select, func, update
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.exc import IntegrityError
from services.query_preparation import PreparationError
from utils.db import db

metadata = MetaData()
cupos = Table('pwa_scraping_cupos', metadata,
    Column('usuario_id', Integer, primary_key=True),
    Column('ejecuciones_habilitadas', Integer, nullable=False))
operaciones = Table('pwa_scraping_operaciones', metadata,
    Column('operacion_id', String(36), primary_key=True), Column('usuario_id', Integer),
    Column('solicitud_hash', String(64)), Column('origen', String(20)),
    Column('estado', String(20)), Column('contexto_json', Text), Column('resultado_json', Text),
    Column('proveedor_trabajo_id', String(160)), Column('creado_en', DateTime),
    Column('actualizado_en', DateTime))
HELD = ('reserved', 'dispatching', 'pending', 'consumed')
TRANSITIONS = {'reserved': {'dispatching', 'released'},
               'dispatching': {'consumed', 'pending', 'released'},
               'pending': {'consumed', 'released'}}


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def fingerprint(prepared):
    payload = {**prepared, 'context': {k: v for k, v in prepared['context'].items() if k != 'fecha'}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class MySQLScrapingQuota:
    def _engine(self):
        if db.engine.dialect.name != 'mysql':
            raise PreparationError('El contador requiere MySQL.', 503)
        return db.engine

    def _lock(self, conn, user_id):
        stmt = insert(cupos).values(usuario_id=user_id, ejecuciones_habilitadas=6)
        conn.execute(stmt.on_duplicate_key_update(usuario_id=stmt.inserted.usuario_id))
        return conn.execute(select(cupos.c.ejecuciones_habilitadas).where(
            cupos.c.usuario_id == user_id).with_for_update()).scalar_one()

    def reserve_direct(self, operation_id, user_id, prepared):
        digest = fingerprint(prepared)
        try:
            with self._engine().begin() as conn:
                total = self._lock(conn, user_id)
                existing = conn.execute(select(operaciones).where(
                    operaciones.c.operacion_id == operation_id).with_for_update()).mappings().first()
                if existing:
                    if existing['usuario_id'] != user_id or existing['solicitud_hash'] != digest:
                        raise PreparationError('El identificador pertenece a otro pedido.', 409)
                    return
                used = conn.execute(select(func.count()).select_from(operaciones).where(
                    operaciones.c.usuario_id == user_id, operaciones.c.estado.in_(HELD))).scalar_one()
                if used >= total:
                    raise PreparationError('No quedan ejecuciones de scraping disponibles.', 402)
                conn.execute(operaciones.insert().values(operacion_id=operation_id, usuario_id=user_id,
                    solicitud_hash=digest, origen=prepared['sources'][0], estado='reserved',
                    contexto_json=json.dumps(prepared, ensure_ascii=False)))
        except IntegrityError:
            raise PreparationError('El identificador de operación ya está registrado.', 409) from None

    def operation(self, operation_id, user_id):
        with self._engine().connect() as conn:
            row = conn.execute(select(operaciones).where(operaciones.c.operacion_id == operation_id,
                operaciones.c.usuario_id == user_id)).mappings().first()
            if not row:
                return None
            outcome = decode(row['resultado_json'])
            return {'operation_id': row['operacion_id'], 'source': row['origen'], 'state': row['estado'],
                    'outcome': json.dumps(outcome) if outcome is not None else None,
                    'prepared': decode(row['contexto_json'])}

    def transition(self, operation_id, user_id, state, payload=None):
        with self._engine().begin() as conn:
            self._lock(conn, user_id)
            row = conn.execute(select(operaciones.c.estado).where(
                operaciones.c.operacion_id == operation_id, operaciones.c.usuario_id == user_id
            ).with_for_update()).first()
            if not row or state not in TRANSITIONS.get(row[0], set()):
                return False
            values = {'estado': state}
            if payload is not None:
                values['resultado_json'] = json.dumps(payload, ensure_ascii=False)
                values['proveedor_trabajo_id'] = payload.get('provider_job_id')
            conn.execute(update(operaciones).where(operaciones.c.operacion_id == operation_id,
                operaciones.c.usuario_id == user_id).values(**values))
            return True

    def credits(self, user_id):
        with self._engine().begin() as conn:
            total = self._lock(conn, user_id)
            counts = dict(conn.execute(select(operaciones.c.estado, func.count()).where(
                operaciones.c.usuario_id == user_id).group_by(operaciones.c.estado)).all())
            rows = conn.execute(select(operaciones.c.operacion_id, operaciones.c.origen, operaciones.c.estado
                ).where(operaciones.c.usuario_id == user_id).order_by(
                operaciones.c.creado_en.desc(), operaciones.c.operacion_id).limit(30)).all()
            reserved = sum(counts.get(state, 0) for state in ('reserved', 'dispatching', 'pending'))
            consumed = counts.get('consumed', 0)
            return {'initial': total, 'available': max(0, total-reserved-consumed),
                    'reserved': reserved, 'consumed': consumed,
                    'operations': [{'operation_id': row[0], 'source': row[1], 'state': row[2]} for row in rows]}

    def grant_test(self, user_id):
        with self._engine().begin() as conn:
            self._lock(conn, user_id)
            conn.execute(update(cupos).where(cupos.c.usuario_id == user_id).values(
                ejecuciones_habilitadas=cupos.c.ejecuciones_habilitadas+6))
