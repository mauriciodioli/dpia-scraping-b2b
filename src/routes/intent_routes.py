"""Independent resolver endpoint; never creates jobs or spends points."""
from flask import Blueprint, jsonify, request, current_app
from services.intent_resolver import resolve
from services.intent_openai import interpret, IntentProviderError

intent_bp = Blueprint('intent_resolver', __name__, url_prefix='/api/consultas')

@intent_bp.post('/resolver-intencion')
def resolve_intention():
    payload=request.get_json(silent=True)
    try:
        # Deterministic checks and explicit-confirmation guard remain authoritative.
        baseline=resolve(payload)
        interpreted=interpret(payload,current_app.config)
        sufficient=interpreted['sufficient'] and bool(interpreted['objective'].strip())
        if payload['situation']=='jobs' and not sufficient:
            state='NEEDS_CLARIFICATION'
        elif not sufficient:
            state='NEEDS_CLARIFICATION'
        else:
            state='CONFIRMED' if payload.get('confirmed') is True and baseline['state']!='NEEDS_CLARIFICATION' else 'READY_TO_CONFIRM'
        # The deterministic gate must not override the model's decision to ask.
        objective=interpreted['objective'].strip() if sufficient else None
        question=(interpreted['question'].strip() or baseline['question'] or '¿Podés aclarar qué necesitás buscar?') if not sufficient else None
        return jsonify(success=True,state=state,domain=baseline['domain'],
            intent=interpreted['intent'].strip() or baseline['intent'],
            objective=objective,question=question,
            confirmation=(f'{objective} ¿Querés que empiece?' if state=='READY_TO_CONFIRM' else None),
            context=baseline['context'],execution_allowed=state=='CONFIRMED')
    except ValueError as exc:
        return jsonify(success=False,error=str(exc)),400
    except IntentProviderError as exc:
        return jsonify(success=False,error=str(exc)),503
