"""Controladores: traducen requests/responses HTTP y delegan en los servicios."""
from flask import current_app, jsonify, request, session

from services.auth_service import AuthError, persist_google_user, verify_google_credential


def local_login_available():
    from urllib.parse import urlsplit
    return (current_app.debug
            and current_app.config.get('LOCAL_DEV_LOGIN_ENABLED') is True
            and bool(current_app.config.get('LOCAL_DEV_LOGIN_EMAIL'))
            and request.remote_addr in ('127.0.0.1', '::1')
            and urlsplit(request.host_url).hostname in ('localhost', '127.0.0.1', '::1'))


def login_local():
    # No arbitrary identity from the browser; never link or modify Google identities.
    if not local_login_available():
        return jsonify(error='Not found'), 404
    if request.headers.get('Origin') != request.host_url.rstrip('/'):
        return jsonify(error='Origen inválido'), 403
    from model.usuario import Usuario
    user = Usuario.query.filter_by(
        correo_electronico=current_app.config['LOCAL_DEV_LOGIN_EMAIL']).one_or_none()
    if user is None or not user.activo:
        return jsonify(error='Configurá un usuario local existente y activo.'), 403
    session.clear()
    session['email'] = user.correo_electronico
    session['user_id'] = user.id
    return jsonify(email=user.correo_electronico, authenticated=True)


def get_auth_config():
    return jsonify({"client_id": current_app.config.get("GOOGLE_CLIENT_ID", ""), "local_dev_login": bool(local_login_available())})


def get_current_session():
    response = jsonify({"email": session.get("email"), "authenticated": bool(session.get("email"))})
    response.headers['Cache-Control'] = 'no-store'
    return response


def login_with_google():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="Solicitud de acceso inválida."), 400
    credential = body.get("credential", "")
    client_id = current_app.config.get("GOOGLE_CLIENT_ID", "")
    try:
        info = verify_google_credential(credential, client_id)
        user = persist_google_user(info)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    session.clear()
    session["email"] = user.correo_electronico
    session["user_id"] = user.id
    return jsonify({"email": user.correo_electronico, "authenticated": True})


def logout():
    session.clear()
    return jsonify({"authenticated": False})
