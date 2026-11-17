"""Deterministic-first intent resolution; model fallback after three vague replies."""
from flask import Blueprint, current_app, jsonify, request
from services.intent_resolver import resolve
from services.intent_openai import interpret, IntentProviderError

intent_bp = Blueprint('intent_resolver', __name__, url_prefix='/api/consultas')

@intent_bp.post('/resolver-intencion')
def resolve_intention():
    try:
        payload = request.get_json(silent=True)
        result = resolve(payload)
        # Confirmation of a previously interpreted objective must not call the model again.
        proposed = payload.get('proposed_objective') if isinstance(payload, dict) else None
        if payload.get('confirmed') is True and isinstance(proposed, str) and proposed.strip() and len(proposed) <= 2000:
            result['objective'] = proposed.strip()
            result['state'] = 'CONFIRMED'
            result['execution_allowed'] = True
            result['needs_ai_interpretation'] = False
            result['question'] = None
            result['confirmation'] = None
            return jsonify(success=True, **result)
        if not result['needs_ai_interpretation']:
            return jsonify(success=True, **result)

        # OpenAI is only a fallback for a third consecutive unresolved answer.
        # Never let a provider outage erase the conversation or block the chat.
        try:
            interpretation = interpret(payload, current_app.config)
        except (IntentProviderError, ValueError) as exc:
            current_app.logger.warning('Intent interpretation fallback unavailable: %s', type(exc).__name__)
            result['question'] = 'Todavía no pude precisar qué querés buscar. ¿Podés describir un ejemplo concreto?'
            result['needs_ai_interpretation'] = False
            result['ai_fallback_unavailable'] = True
            return jsonify(success=True, **result)

        if interpretation['sufficient'] and interpretation['objective'].strip():
            result['state'] = 'READY_TO_CONFIRM'
            result['objective'] = interpretation['objective']
            result['question'] = None
            result['confirmation'] = interpretation['objective'] + ' ¿La tarea está lista o querés agregar algo más?'
            result['task_preview'].update({
                'task_title': interpretation['task_title'],
                'search_type': interpretation['search_type'],
                'search_market': interpretation['search_market'],
                'product_category': interpretation['product_category'],
                'budget': interpretation['budget'],
                'expected_result': interpretation['expected_result'],
                'missing_required': []
            })
        else:
            result['question'] = interpretation['question'].strip() or result['question']
            result['task_preview']['missing_required'] = interpretation['missing_required']
        result['needs_ai_interpretation'] = False
        result['ai_fallback_used'] = True
        result['execution_allowed'] = False
        return jsonify(success=True, **result)
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
