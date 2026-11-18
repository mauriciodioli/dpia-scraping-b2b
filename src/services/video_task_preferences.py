"""Validate user-facing video task preferences without provider side effects."""
from services.agent_configuration import bad

FIELDS = {
    'script': {'instructions': 5000, 'custom_script': 20000},
    'production': {'video_type': 80, 'language': 20, 'format': 20,
                   'provider': 80, 'avatar_id': 160, 'voice_id': 160},
}

def validate_video_preferences(section, payload):
    if section not in FIELDS or not isinstance(payload, dict):
        bad('Configuración de video inválida.', 422)
    allowed = set(FIELDS[section]) | {'expected_revision'}
    if section == 'production':
        allowed |= {'duration_seconds', 'budget_credits', 'automatic_production'}
    if set(payload) - allowed or type(payload.get('expected_revision')) is not int or payload['expected_revision'] < 1:
        bad('Configuración de video inválida.', 422)
    result = {'expected_revision': payload['expected_revision']}
    for field, limit in FIELDS[section].items():
        value = payload.get(field, '')
        if not isinstance(value, str) or len(value) > limit:
            bad('Campo de video inválido: ' + field, 422)
        result[field] = value
    if section == 'production':
        duration = payload.get('duration_seconds', 60)
        budget = payload.get('budget_credits', 0)
        automatic = payload.get('automatic_production', False)
        if type(duration) is not int or not 1 <= duration <= 3600 or type(budget) is not int or not 0 <= budget <= 1000000 or type(automatic) is not bool:
            bad('Límites de video inválidos.', 422)
        result.update(duration_seconds=duration, budget_credits=budget, automatic_production=automatic)
    return result
