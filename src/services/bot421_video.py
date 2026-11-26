"""Owner-scoped workspace adapter for the verified BOT421 publication."""

import os
import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from flask import current_app

from services.agent_activation import video_resources, video_quote
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
    store = current_app.extensions.get('agent_configuration_store') or AgentConfigurationStore()
    try:
        task = store.prepare_publication_video(owner, publication_id)
        prefs = VideoTaskPreferences()
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
