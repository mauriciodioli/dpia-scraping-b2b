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
    store = current_app.extensions.get('agent_configuration_store') or AgentConfigurationStore()
    try:
        task = store.prepare_publication_video(owner, publication_id)
        prefs = VideoTaskPreferences()
        if action == 'quote':
            return video_quote(owner, task['agent_id'], task['id'], {k:body[k] for k in ('duration','format','language','avatar_id','voice_id')})
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
