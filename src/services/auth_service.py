"""Lógica de negocio para la autenticación con Google."""
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


class AuthError(Exception):
    """Error de autenticación con un mensaje y código HTTP asociados."""

    def __init__(self, message, status_code=401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def verify_google_credential(credential, client_id):
    """Verifica un credential de Google Sign-In y devuelve la información del usuario."""
    if not client_id:
        raise AuthError("Google OAuth no está configurado", 503)
    try:
        info = id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)
    except ValueError as exc:
        raise AuthError("Credencial Google inválida", 401) from exc
    if not info.get("email_verified"):
        raise AuthError("Email sin verificar", 401)
    return info
