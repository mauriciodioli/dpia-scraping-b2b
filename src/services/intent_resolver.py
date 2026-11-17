"""Deterministic, side-effect-free first-stage intent resolver for start/jobs.
Publication taxonomy/location is intentionally excluded from search constraints.
"""
import re

SITUATIONS = {'start', 'jobs'}
ACTIONS = {'search', 'explore', 'novel', 'local'}
JOB_HINT = re.compile(r'\b(python|java|javascript|react|backend|frontend|full.?stack|developer|desarrollador|programador|ingenier[oa]|enfermer[oa]|camarer[oa]|hotel|recepcionista|administrativ[oa]|contador|docente|profesor|diseñador|marketing|ventas|vendedor|chofer|conductor|mecanic[oa]|electricista|plomer[oa]|data|analista|qa|tester|devops|empleos? de|trabajo de|puesto de|vacantes? de)\b', re.I)
COMMERCIAL_HINT = re.compile(r'\b(pantalones?|tel[eé]fonos?|celulares?|ropa|calzado|zapatillas?|herramientas?|ferreter[ií]a|electr[oó]nica|juguetes?|perfumes?|cosm[eé]ticos?|alimentos?|accesorios?|proveedores?|mayoristas?|productos?|tendencias?|demanda|precios?|margen|importar|revender)\b', re.I)

def resolve(payload):
    if not isinstance(payload, dict):
        raise ValueError('invalid_payload')
    situation = payload.get('situation')
    action = payload.get('action', 'search')
    if situation not in SITUATIONS or action not in ACTIONS:
        raise ValueError('unsupported_journey')
    message = str(payload.get('message') or '').strip()[:3000]
    answers = payload.get('answers') or []
    if not isinstance(answers, list) or len(answers) > 12 or any(not isinstance(x, str) for x in answers):
        raise ValueError('invalid_answers')
    answer_text = ' '.join(x.strip()[:1000] for x in answers)
    combined = ' '.join(filter(None, [message, answer_text]))
    confirmed = payload.get('confirmed') is True
    if situation == 'jobs':
        intent = 'find_recent_jobs' if action == 'novel' else 'find_local_jobs' if action == 'local' else 'find_jobs'
        sufficient = bool(JOB_HINT.search(combined))
        question = '¿Qué tipo de trabajo o puesto estás buscando?'
        objective = f'Buscar oportunidades laborales {"recientes " if action == "novel" else ""}según este pedido: {combined}.'
    else:
        intent = {'explore':'discover_resale_products','novel':'discover_trending_products','local':'discover_local_resale_opportunities','search':'resale_research'}[action]
        sufficient = action != 'search' or bool(COMMERCIAL_HINT.search(combined))
        question = '¿Querés descubrir productos para revender, encontrar proveedores o comparar precios?'
        base = {'explore':'Investigar productos con potencial de reventa', 'novel':'Investigar novedades y tendencias para reventa', 'local':'Investigar oportunidades comerciales locales', 'search':'Investigar oportunidades de reventa'}[action]
        objective = base + (f'. Pedido: {combined}.' if combined else '.')
    state = 'CONFIRMED' if sufficient and confirmed else 'READY_TO_CONFIRM' if sufficient else 'NEEDS_CLARIFICATION'
    return {'state':state,'domain':'employment' if situation=='jobs' else 'commerce',
            'intent':intent,'objective':objective if sufficient else None,
            'question':question if not sufficient else None,
            'confirmation':f'{objective} ¿Querés que empiece?' if sufficient and not confirmed else None,
            'context':{'situation':situation,'action':action},
            'execution_allowed':state=='CONFIRMED'}
