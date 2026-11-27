"""Owner-scoped workspace adapter for the verified BOT421 publication."""

import os
import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN

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
                        'equivalent':money(r.get('amount',0) if r['source']=='recarga' else r['cost']),
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
            from decimal import ROUND_CEILING
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
            points = int((Decimal(quote['amount']) / Decimal(quote['usd_per_credit'])).to_integral_value(rounding=ROUND_CEILING))
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
                    if previous.get('configuration') != {**configuration,'background':body['background'],'script':script}:
                        bad('Solicitud duplicada con otra configuración.', 409)
                else:
                    if revision != body['expected_revision']:
                        bad('La configuración cambió.', 409)
                    if quota.credits(owner)['available'] < points:
                        bad('Saldo insuficiente.', 402)
                    video = dict(params.get('video') or {})
                    video.update(script=script, production=production)
                    params.update(video=video, _configuration_revision=revision+1,
                        _publication_execution={'key':body['idempotency_key'],
                            'configuration':{**configuration,'background':body['background'],'script':script}})
                    conn.execute(update(tables['agente_tareas']).where(tables['agente_tareas'].c.id==task['id'])
                        .values(parametros=params, habilitada=True, actualizado_en=datetime.now(timezone.utc).replace(tzinfo=None)))
            result = schedule_immediate_task(owner, task['agent_id'], task['id'], body['idempotency_key'], existing=True)
            return {'state':'SCHEDULED','task_id':task['id'],'schedule':result['schedule'],'replayed':result['replayed']}
        if action == 'quote':
            quote = video_quote(owner, task['agent_id'], task['id'], {k:body[k] for k in ('duration','format','language','avatar_id','voice_id')})
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
        import json
        params = row['parametros'] if row else {}
        if isinstance(params, str):
            params = json.loads(params)
        key = (params.get('_publication_execution') or {}).get('key')
        if not key:
            return {'state':'IDLE'}
        schedule = str(uuid5(NAMESPACE_URL, 'immediate-task:'+str(owner)+':'+key))
        run = conn.execute(text("""
            SELECT j.id, j.state, j.error_code
            FROM ae_schedules s LEFT JOIN ae_jobs j
              ON j.schedule_id=s.id AND j.owner_id=s.owner_id
              AND j.legacy_task_id=s.legacy_task_id AND j.agent_id=s.agent_id
            WHERE s.id=:schedule AND s.owner_id=:owner AND s.legacy_task_id=:task
            ORDER BY j.created_at DESC LIMIT 1
        """), dict(schedule=schedule, owner=owner, task=row['id'])).mappings().first()
        if run is None:
            return {'state':'UNCONFIRMED','schedule_id':schedule}
        result = {'schedule_id':schedule,'job_id':run['id'],'state':run['state'] or 'SCHEDULED'}
        if run['error_code']:
            result['reason_code'] = run['error_code']
        if run['state'] == 'DELIVERED':
            payload = conn.execute(text("""
                SELECT payload FROM ae_results WHERE owner_id=:owner AND job_id=:job
                ORDER BY version DESC LIMIT 1
            """), dict(owner=owner, job=run['id'])).scalar()
            if isinstance(payload, str):
                payload = json.loads(payload)
            video = (payload or {}).get('video') or {}
            if video.get('state') == 'COMPLETED' and video.get('url'):
                result.update(state='COMPLETED', video_url=video['url'])
        return result
