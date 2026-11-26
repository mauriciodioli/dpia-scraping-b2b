"""BOT421 video identity delegation through the existing B2B email service."""
import hashlib
import hmac
import json
import os
import re
import time
from uuid import UUID

from flask import Blueprint, current_app, jsonify, request

from model.publicaciones.publicaciones import Publicacion
from model.usuario import Usuario
from services import email_login

bot421_auth = Blueprint('bot421_auth', __name__, url_prefix='/api/internal/bot421/auth')


@bot421_auth.after_request
def no_store(response):
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def canonical_uuid(value):
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def authorization(redis, grant):
    expiration = redis.get(grant)
    if expiration:
        return {'authorized': True, 'expires_at': int(expiration)}
    return None


def send_challenge(redis, secret, mail_host, sender, key, email, resend, idem, saved):
    existing = redis.hgetall(key)
    if existing and not resend:
        redis.set(idem, saved, ex=600)
        return
    if not email_login.allow_attempt(redis, secret, 'email:' + email.lower(), 4):
        return {'error': 'rate_limited'}, 429

    code = email_login.new_code()
    # Store the digest only after SMTP accepts the message. A failed resend preserves
    # the previous code and counters. The per-session lock covers issue and verify.
    email_login.send_mail(mail_host, sender, email, code)
    with redis.pipeline(transaction=True) as pipe:
        pipe.hset(key, mapping={'digest': email_login.digest(secret, key, code), 'attempts': '0'})
        pipe.expire(key, 600)
        pipe.set(idem, saved, ex=600)
        pipe.execute()


@bot421_auth.post('/billing_topup_settle', defaults={'action': 'billing_topup_settle'})
@bot421_auth.post('/billing_topup_quote', defaults={'action': 'billing_topup_quote'})
@bot421_auth.post('/billing_credit', defaults={'action': 'billing_credit'})
@bot421_auth.post('/billing', defaults={'action': 'billing'})
@bot421_auth.post('/quote', defaults={'action': 'quote'})
@bot421_auth.post('/workspace', defaults={'action': 'workspace'})
@bot421_auth.post('/resources', defaults={'action': 'resources'})
@bot421_auth.post('/script', defaults={'action': 'script'})
@bot421_auth.post('/status', defaults={'action': 'status'})
@bot421_auth.post('/start', defaults={'action': 'start'})
@bot421_auth.post('/verify', defaults={'action': 'verify'})
def delegate(action):
    secret = os.environ.get('DPIA_BOT421_B2B_HMAC_SECRET', '').encode()
    if len(secret) < 32:
        return jsonify(error='unavailable'), 503
    stamp = request.headers.get('X-DPIA-Timestamp', '')
    nonce = request.headers.get('X-DPIA-Request-ID', '')
    signature = request.headers.get('X-DPIA-Signature', '')
    now = int(time.time())
    if not re.fullmatch(r'[0-9]{1,12}', stamp) or abs(now - int(stamp)) > 60 or not canonical_uuid(nonce):
        return jsonify(error='invalid_signature'), 401
    if not request.is_json or not 0 < (request.content_length or 0) <= (60000 if action == 'script' else 2048):
        return jsonify(error='invalid_request'), 400
    raw = request.get_data(cache=True)
    signed = '\n'.join(('POST', request.path, stamp, nonce)).encode() + b'\n' + raw
    expected = hmac.new(secret, signed, hashlib.sha256).hexdigest()
    if not re.fullmatch(r'[a-f0-9]{64}', signature) or not hmac.compare_digest(expected, signature):
        return jsonify(error='invalid_signature'), 401

    body = request.get_json(silent=True)
    if action == 'billing_topup_settle':
        return settle_topup(body)
    required = {'usuario_id', 'publicacion_id', 'session_ref', 'jwt_exp'}
    if action in ('start', 'verify', 'billing_credit'):
        required.add('idempotency_key')
    if action == 'billing_topup_quote' and isinstance(body, dict) and 'amount_cents' in body:
        required.add('amount_cents')
    if action == 'resources':
        required.add('language')
    if action == 'quote':
        required.update(('duration','format','language','avatar_id','voice_id'))
    if action == 'script':
        required.update(('expected_revision', 'custom_script', 'instructions'))
    if action == 'start':
        required.add('resend')
    if action == 'verify':
        required.add('code')
    if not isinstance(body, dict) or set(body) != required:
        return jsonify(error='invalid_request'), 400
    if (any(type(body[key]) is not int or body[key] <= 0 for key in ('usuario_id', 'publicacion_id', 'jwt_exp'))
            or not isinstance(body['session_ref'], str) or not re.fullmatch(r'[a-f0-9]{64}', body['session_ref'])
            or (action in ('start', 'verify', 'billing_credit') and not canonical_uuid(body['idempotency_key']))
            or (action == 'start' and type(body['resend']) is not bool)
            or (action == 'verify' and (not isinstance(body['code'], str) or not re.fullmatch(r'[0-9]{8}', body['code'])))):
        return jsonify(error='invalid_request'), 400
    if body['jwt_exp'] <= now:
        return jsonify(error='session_expired'), 401

    try:
        redis, code_secret, host, sender = email_login.setup()
        if not redis.set('dpia:bot421:nonce:' + nonce, '1', ex=125, nx=True):
            return jsonify(error='replay'), 409
        owner = body['usuario_id']
        user = Usuario.query.filter_by(id=owner, activo=True).first()
        if not user or not Publicacion.query.filter_by(id=body['publicacion_id'], user_id=owner).first():
            return jsonify(error='forbidden'), 403
        email = user.correo_electronico.strip() if user.correo_electronico else ''
        if len(email) > 120 or not email_login.EMAIL.fullmatch(email):
            return jsonify(error='email_unavailable'), 409
        local, domain = email.rsplit('@', 1)
        masked = local[0] + '***@' + domain
        # Authorization is for this original BOT421 session and owner. Publication
        # ownership is verified separately on every request, including status.
        scope = email_login.digest(code_secret, str(owner), body['session_ref'], email.lower())
        prefix = 'dpia:bot421:video:' + scope
        grant = prefix + ':grant'
        challenge = prefix + ':code'
        if action in ('workspace', 'resources', 'script', 'quote', 'billing', 'billing_credit', 'billing_topup_quote'):
            if not authorization(redis, grant):
                return jsonify(error='verification_required'), 403
            if action == 'resources' and body['language'] not in ('es', 'en', 'it'):
                return jsonify(error='invalid_request'), 400
            if action == 'script' and (
                type(body['expected_revision']) is not int
                or not isinstance(body['custom_script'], str) or len(body['custom_script']) > 20000
                or not isinstance(body['instructions'], str) or len(body['instructions']) > 5000
            ):
                return jsonify(error='invalid_request'), 400
            from services.bot421_video import dispatch
            result = dispatch(action, owner, body['publicacion_id'], body)
            if isinstance(result, tuple):
                return jsonify(result[0]), result[1]
            return jsonify(result)

        if action == 'status':
            return jsonify(authorization(redis, grant) or {
                'authorized': False, 'pending': redis.ttl(challenge) > 0, 'email_mask': masked,
            })

        with redis.lock(prefix + ':lock', timeout=45, blocking_timeout=3):
            authorized = authorization(redis, grant)
            if authorized:
                return jsonify(authorized)
            idem = prefix + ':retry:' + action + ':' + body['idempotency_key']
            fingerprint = email_login.digest(code_secret, raw.decode())
            previous = redis.get(idem)
            if previous:
                saved = json.loads(previous)
                if saved['fingerprint'] != fingerprint:
                    return jsonify(error='idempotency_conflict'), 409
                return jsonify(saved['result']), saved['status']
            if action == 'start':
                result = {'authorized': False, 'pending': True, 'email_mask': masked}
                saved = json.dumps({'fingerprint': fingerprint, 'result': result, 'status': 200})
                failure = send_challenge(redis, code_secret, host, sender, challenge, email, body['resend'], idem, saved)
                if failure:
                    result, status = failure
                    redis.set(idem, json.dumps({'fingerprint': fingerprint, 'result': result, 'status': status}), ex=600)
                else:
                    status = 200
            else:
                expiration = min(body['jwt_exp'], int(time.time()) + 86400)
                if expiration <= int(time.time()):
                    return jsonify(error='session_expired'), 401
                invalid = {'error': 'invalid_code'}
                failed = json.dumps({'fingerprint': fingerprint, 'result': invalid, 'status': 401})
                accepted = redis.eval(email_login.VERIFY, 3, challenge, grant, idem,
                                      email_login.digest(code_secret, challenge, body['code']), expiration, failed)
                result, status = ({'authorized': True, 'expires_at': expiration}, 200) if accepted else (invalid, 401)
            return jsonify(result), status
    except Exception as exc:
        current_app.logger.warning('BOT421 delegated authentication unavailable: %s', type(exc).__name__)
        return jsonify(error='unavailable'), 503


def settle_topup(body):
    # The shared BOT421 service HMAC above authenticates the provider verifier.
    # Settlement must be possible after the payer's browser session has ended.
    from sqlalchemy.exc import SQLAlchemyError
    from services.query_preparation import PreparationError
    from services.scraping_quota import MySQLScrapingQuota

    required = {'usuario_id', 'order_id', 'capture_id', 'expected_cents', 'paid_cents',
                'currency', 'points', 'usd_per_credit', 'policy_revision', 'provider'}
    if (not isinstance(body, dict) or set(body) != required
            or any(type(body[key]) is not int or not 0 < body[key] <= 2147483647 for key in
                   ('usuario_id', 'expected_cents', 'paid_cents', 'points', 'policy_revision'))
            or body['provider'] not in ('stripe', 'paypal', 'mercadopago')
            or not isinstance(body['usd_per_credit'], str)
            or not re.fullmatch(r'[0-9]{1,12}(?:[.][0-9]{1,18})?', body['usd_per_credit'])
            or any(not isinstance(body[key], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', body[key])
                   for key in ('order_id', 'capture_id'))):
        return jsonify(error='invalid_request'), 400
    quota = current_app.extensions.get('scraping_quota') or MySQLScrapingQuota()
    try:
        return jsonify(quota.credit_verified_payment(body['usuario_id'],
                       {key: body[key] for key in required - {'usuario_id'}}))
    except PreparationError as error:
        return jsonify(error='credit_failed'), error.status
    except SQLAlchemyError:
        current_app.logger.warning('Service top-up settlement unavailable')
        return jsonify(error='unavailable'), 503
