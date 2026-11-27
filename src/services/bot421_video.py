"""Owner-scoped workspace adapter for the verified BOT421 publication."""

import base64
import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from urllib.parse import parse_qs, urlsplit

from flask import current_app

from services.agent_activation import video_resources, video_quote, schedule_immediate_task
from services.agent_configuration import AgentConfigurationStore
from services.query_preparation import PreparationError
from services.scraping_quota import MySQLScrapingQuota
from services.video_task_preferences import VideoTaskPreferences


def monetary_balance(user_id):
    currency = os.environ.get('DPIA_VIDEO_COMMERCIAL_CURRENCY', '')
    version = os.environ.get('DPIA_VIDEO_COMMERCIAL_VERSION', '')
    try:
        rate = Decimal(os.environ.get('DPIA_VIDEO_COMMERCIAL_AMOUNT_PER_POINT', ''))
        if not re.fullmatch(r'[A-Z]{3}', currency) or not version or not rate.is_finite() or not 0 < rate <= 100000:
            return None
        minor = int(os.environ.get('DPIA_VIDEO_COMMERCIAL_MINOR_UNITS', '2'))
        if not 0 <= minor <= 3:
            return None
    except (InvalidOperation, ValueError):
        return None
    quota = current_app.extensions.get('scraping_quota') or MySQLScrapingQuota()
    amount = (quota.credits(user_id)['available'] * rate).quantize(Decimal(1).scaleb(-minor), rounding=ROUND_DOWN)
    return {'currency': currency, 'amount': str(amount), 'policy_version': version}


def dispatch(action, owner, publication_id, body):
    if action == 'billing_topup_quote':
        from services.scraping_quota import TOPUP_PACKAGES, topup_package
        if body.get('amount_cents') is None:
            return {'packages': [topup_package(cents) for cents in TOPUP_PACKAGES]}
        try:
            return topup_package(body['amount_cents'])
        except PreparationError as error:
            return {'error': 'invalid_amount'}, error.status
    if action in ('billing', 'billing_credit'):
        from services.scraping_quota import Usuario, db
        user = db.session.get(Usuario, owner)
        can_credit = bool(user and user.activo and str(user.roll or '').strip().casefold() in {'administrador','admin'})
        if action == 'billing_credit':
            if not can_credit:
                return {'error':'forbidden'}, 403
            quota = current_app.extensions.get('scraping_quota') or MySQLScrapingQuota()
            try:
                return quota.grant_points(owner, 6, body['idempotency_key'], admin_only=True)
            except PreparationError as exc:
                return {'error':'credit_failed'}, exc.status
        from services.agent_activation import billing_policy
        try:
            rate, revision = billing_policy(owner)
            quota = current_app.extensions.get('scraping_quota') or MySQLScrapingQuota()
            summary = quota.credits(owner)
            money = lambda n: str((Decimal(n)*rate).quantize(Decimal('0.01'), rounding=ROUND_DOWN))
            return {'currency':'USD','policy_version':str(revision),
                    'can_virtual_credit':can_credit, 'virtual_credit_amount':money(6),
                    'available':money(summary['available']), 'allocated':money(summary['initial']),
                    'consumed':money(summary['consumed']), 'reserved':money(summary['reserved']),
                    'movements':[{'id':r['operation_id'],'source':r['source'],'state':r['state'],
                        'equivalent':(r.get('settled_amount') or r.get('authorized_amount')) if r.get('grouped') else money(r.get('amount',0) if r['source']=='recarga' else r['cost']),
                        **({k:r[k] for k in ('grouped','reserved_points','consumed_points','released_points','created_at','job_id','result_id')}
                           if r.get('grouped') else {}),
                        **({'paid_cents': r['paid_cents'], 'points': r['amount']} if 'paid_cents' in r else {})}
                        for r in summary['operations']], 'history_limit':30}
        except PreparationError as exc:
            return {'error':'billing_unavailable'}, exc.status
    if action == 'generation_status':
        return generation_status(owner, publication_id)
    store = current_app.extensions.get('agent_configuration_store') or AgentConfigurationStore()
    try:
        task = store.prepare_publication_video(owner, publication_id)
        prefs = VideoTaskPreferences()
        if action == 'generate':
            from services.video_task_preferences import validate
            from sqlalchemy import update
            from datetime import datetime, timezone
            from services.agent_configuration import bad
            configuration = {k: body[k] for k in ('duration','format','language','avatar_id','voice_id')}
            if (type(body['duration']) is not int or body['duration'] not in (15,30,60)
                    or body['format'] not in ('16:9','9:16','1:1') or body['language'] not in ('es','en','it')
                    or type(body['expected_revision']) is not int):
                bad('Configuración inválida.', 422)
            script = validate('script', {k:body[k] for k in ('custom_script','instructions')})
            if not script['custom_script'].strip():
                bad('Ingresá un guion.', 422)
            production = validate('production', {'duration_seconds':body['duration'],
                'format':body['format'], 'language':body['language'], 'avatar_id':body['avatar_id'],
                'voice_id':body['voice_id'], 'background':body['background'], 'automatic_production':True})
            quote = video_quote(owner, task['agent_id'], task['id'], configuration)
            accepted = body.get('accepted_quote')
            if 'accepted_quote' in body and (not isinstance(accepted, dict)
                    or type(accepted.get('policy_revision')) is not int):
                bad('Cotización inválida.', 422)
            commercial = {key: quote[key] for key in ('amount', 'currency', 'usd_per_credit', 'policy_revision')}
            if isinstance(accepted, dict) and 'pricing_model' in accepted:
                commercial.update(pricing_model='duration', authorized_seconds=body['duration'],
                    duration_base_amount=quote['estimated_usd'])
            points = quote['required_credits']
            quota = current_app.extensions.get('scraping_quota') or MySQLScrapingQuota()
            production['budget_credits'] = points
            with prefs.repository.transaction(owner, task['agent_id']) as (conn, tables, agent):
                row = next((r for r in prefs.repository.tasks(conn, tables, task['agent_id']) if r['id']==task['id']), None)
                if not row or row['tipo'] != 'VIDEO_GENERAR':
                    bad('Tarea no disponible.', 404)
                params = dict(row['parametros'] or {})
                revision = params.get('_configuration_revision', 1)
                previous = params.get('_publication_execution')
                if previous and previous.get('key') == body['idempotency_key']:
                    previous_quote = previous.get('commercial')
                    if (previous.get('configuration') != {**configuration,'background':body['background'],'script':script}
                            or accepted != ({key: previous_quote.get(key) for key in commercial} if previous_quote else None)):
                        bad('Solicitud duplicada con otra configuración.', 409)
                else:
                    if accepted is not None and accepted != commercial:
                        bad('La cotización cambió.', 409)
                    if revision != body['expected_revision']:
                        bad('La configuración cambió.', 409)
                    if quota.credits(owner)['available'] < points:
                        bad('Saldo insuficiente.', 402)
                    video = dict(params.get('video') or {})
                    video.update(script=script, production=production)
                    params.update(video=video, _configuration_revision=revision+1,
                        _publication_execution={'key':body['idempotency_key'],
                            'configuration':{**configuration,'background':body['background'],'script':script},
                            **({'commercial': {**commercial, 'points': points}} if accepted else {})})
                    conn.execute(update(tables['agente_tareas']).where(tables['agente_tareas'].c.id==task['id'])
                        .values(parametros=params, habilitada=True, actualizado_en=datetime.now(timezone.utc).replace(tzinfo=None)))
            result = schedule_immediate_task(owner, task['agent_id'], task['id'], body['idempotency_key'], existing=True)
            return {'state':'SCHEDULED','task_id':task['id'],'schedule':result['schedule'],'replayed':result['replayed']}
        if action == 'quote':
            quote = video_quote(owner, task['agent_id'], task['id'], {k:body[k] for k in ('duration','format','language','avatar_id','voice_id')})
            quote.update(pricing_model='duration', authorized_seconds=body['duration'],
                         duration_base_amount=quote['estimated_usd'])
            quota = current_app.extensions.get('scraping_quota') or MySQLScrapingQuota()
            try:
                summary = quota.credits(owner)
                rate = Decimal(quote['usd_per_credit'])
                money = lambda n: str((Decimal(n)*rate).quantize(Decimal('0.01'), rounding=ROUND_DOWN))
                quote['balance'] = {'currency':'USD','amount':money(summary['available']),
                    'allocated':money(summary['initial']), 'consumed':money(summary['consumed']),
                    'reserved':money(summary['reserved']), 'policy_version':str(quote['policy_revision'])}
            except Exception:
                current_app.logger.warning('BOT421 billing balance unavailable')
                quote['balance'] = None
            return quote
        if action == 'resources':
            return video_resources(owner, task['agent_id'], task['id'], body['language'])
        if action == 'script':
            return prefs.section(owner, task['agent_id'], task['id'], 'script', {
                'expected_revision': body['expected_revision'],
                'values': {'custom_script': body['custom_script'], 'instructions': body['instructions']},
            })
        return {'script': prefs.section(owner, task['agent_id'], task['id'], 'script'),
                'balance': monetary_balance(owner)}
    except PreparationError as exc:
        return {'error': 'video_operation_unavailable', 'message': str(exc)}, exc.status


def generation_status(owner, publication_id):
    """Read the exact latest publication request, never a recurring task's latest job."""
    from uuid import uuid5, NAMESPACE_URL
    from sqlalchemy import text
    from utils.db import db
    with db.engine.connect() as conn:
        row = conn.execute(text("""
            SELECT t.id, t.parametros
            FROM agente_tareas t JOIN agentes a ON a.id=t.agente_id
            WHERE a.usuario_id=:owner AND t.tipo='VIDEO_GENERAR'
              AND JSON_UNQUOTE(JSON_EXTRACT(t.parametros,'$.source.publication_id'))=:publication
            ORDER BY t.id DESC LIMIT 1
        """), dict(owner=owner, publication=str(publication_id))).mappings().first()
        params = row['parametros'] if row else {}
        if isinstance(params, str):
            params = json.loads(params)
        key = (params.get('_publication_execution') or {}).get('key')
        if not key:
            return {'state':'IDLE'}
        schedule = str(uuid5(NAMESPACE_URL, 'immediate-task:'+str(owner)+':'+key))
        run = conn.execute(text("""
            SELECT j.id, j.state, j.error_code, j.finished_at
            FROM ae_schedules s LEFT JOIN ae_jobs j
              ON j.schedule_id=s.id AND j.owner_id=s.owner_id
              AND j.legacy_task_id=s.legacy_task_id AND j.agent_id=s.agent_id
            WHERE s.id=:schedule AND s.owner_id=:owner AND s.legacy_task_id=:task
            ORDER BY j.created_at DESC LIMIT 1
        """), dict(schedule=schedule, owner=owner, task=row['id'])).mappings().first()
        if run is None:
            return {'state':'UNCONFIRMED','schedule_id':schedule}
        result = {'schedule_id': schedule, 'job_id': run['id'], 'state': run['state'] or 'SCHEDULED'}
        if run['finished_at']:
            result['finished_at'] = run['finished_at'].isoformat() + 'Z'
        if run['error_code']:
            result['reason_code'] = run['error_code']
        if run['state'] == 'DELIVERED':
            payload = conn.execute(text("""
                SELECT payload FROM ae_results WHERE owner_id=:owner AND job_id=:job
                ORDER BY version DESC LIMIT 1
            """), dict(owner=owner, job=run['id'])).scalar()
            url = _completed_video_url(payload)
            if url:
                result.update(state='COMPLETED', video_url=url)
        return result


def generation_notifications(owner=None, publications=None):
    """Recover terminal publication jobs from persisted immediate schedules."""
    from sqlalchemy import bindparam, text
    from utils.db import db

    public = publications is not None
    scope = """p.id IN :publications AND LOWER(p.estado)='activo' AND j.state='DELIVERED'
        AND NOT EXISTS (SELECT 1 FROM estado_publi_usu e
                        WHERE e.publicacion_id=p.id AND e.estado='eliminado')""" if public else 'j.owner_id=:owner'
    with db.engine.connect() as conn:
        statement = text(f"""
            SELECT j.id, j.state, j.error_code, j.finished_at, p.id AS publication_id,
                   CASE WHEN j.state = 'DELIVERED' THEN (
                       SELECT r.payload FROM ae_results r
                       WHERE r.owner_id=j.owner_id AND r.job_id=j.id
                       ORDER BY r.version DESC LIMIT 1
                   ) END AS payload
            FROM ae_jobs j
            JOIN ae_schedules s ON s.id=j.schedule_id AND s.owner_id=j.owner_id
                AND s.agent_id=j.agent_id AND s.legacy_task_id=j.legacy_task_id
            JOIN agente_tareas t ON t.id=j.legacy_task_id AND t.tipo='VIDEO_GENERAR'
            JOIN agentes a ON a.id=t.agente_id AND a.usuario_id=j.owner_id
            JOIN publicacion p ON p.user_id=j.owner_id AND
                p.id=JSON_UNQUOTE(JSON_EXTRACT(t.parametros,'$.source.publication_id'))
            WHERE {scope} AND j.finished_at IS NOT NULL
              AND j.state IN ('DELIVERED', 'FAILED', 'CANCELLED')
              AND JSON_UNQUOTE(JSON_EXTRACT(t.parametros,'$.source.application'))='bot421'
              AND EXISTS (
                  SELECT 1 FROM ae_agent_events e
                  WHERE e.owner_id=j.owner_id AND e.agent_id=j.agent_id
                    AND e.action='TASK_SCHEDULE_CREATED'
                    AND JSON_UNQUOTE(JSON_EXTRACT(e.details,'$.immediate'))='true'
                    AND JSON_UNQUOTE(JSON_EXTRACT(e.details,'$.schedule_id'))=s.id
              )
            ORDER BY j.finished_at, j.id
        """)
        if public:
            statement = statement.bindparams(bindparam('publications', expanding=True))
        rows = conn.execute(statement, {'publications': publications} if public else {'owner': owner}).mappings()

        executions = []
        for row in rows:
            url = _completed_video_url(row['payload'])
            if row['state'] == 'DELIVERED' and not url:
                continue
            execution = {
                'job_id': row['id'], 'publication_id': row['publication_id'],
                'state': 'COMPLETED' if url else row['state'], 'reason_code': row['error_code'],
                'finished_at': row['finished_at'].isoformat() + 'Z',
            }
            if url:
                execution['cover'] = _temporary_cover(url)
            executions.append(execution)
        if public:
            latest = {item['publication_id']: item['cover'] for item in executions}
            return {key: cover for key, cover in latest.items() if cover}
        return executions


def _temporary_cover(url):
    if not isinstance(url, str) or any(ord(char) <= 32 for char in url):
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None:
            return None
        fields = {key.lower(): value[0] for key, value in parse_qs(parsed.query).items()}
        expiry = _signed_url_expiry(fields)
    except (ValueError, OverflowError, OSError, KeyError, TypeError):
        return None
    if expiry and expiry <= datetime.now(timezone.utc):
        return None
    return {'url': url, 'expires_at': expiry.isoformat() if expiry else None}


def _signed_url_expiry(fields):
    for prefix in ('x-amz-', 'x-goog-'):
        if prefix + 'expires' in fields:
            start = datetime.strptime(fields[prefix + 'date'], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            return start + timedelta(seconds=int(fields[prefix + 'expires']))
    if 'policy' in fields and 'key-pair-id' in fields:
        policy = fields['policy'].translate(str.maketrans('-_~', '+=/'))
        statements = json.loads(base64.b64decode(policy))['Statement']
        return min(datetime.fromtimestamp(item['Condition']['DateLessThan']['AWS:EpochTime'], timezone.utc)
                   for item in statements)
    if 'expires' in fields:
        return datetime.fromtimestamp(int(fields['expires']), timezone.utc)
    return None


def _completed_video_url(payload):
    if isinstance(payload, str):
        payload = json.loads(payload)
    video = (payload or {}).get('video') or {}
    return video.get('url') if video.get('state') == 'COMPLETED' else None
