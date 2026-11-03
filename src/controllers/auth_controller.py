"""Controladores: traducen requests/responses HTTP y delegan en los servicios."""
from flask import current_app, jsonify, request, session

from services.auth_service import AuthError, verify_google_credential


def get_auth_config():
    return jsonify({"client_id": current_app.config.get("GOOGLE_CLIENT_ID", "")})


def get_current_session():
    return jsonify({"email": session.get("email"), "authenticated": bool(session.get("email"))})


def login_with_google():
    credential = (request.get_json(silent=True) or {}).get("credential", "")
    client_id = current_app.config.get("GOOGLE_CLIENT_ID", "")
    try:
        info = verify_google_credential(credential, client_id)
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    session.clear()
    session["email"] = info["email"]
    return jsonify({"email": info["email"], "authenticated": True})


def logout():
    session.clear()
    return jsonify({"authenticated": False})
