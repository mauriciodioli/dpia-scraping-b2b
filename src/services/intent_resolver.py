"""Side-effect-free deterministic resolver for the currently supported B2B journeys.

The user confirms uncertain but usable requests; no model call is required.
"""
import re

SITUATIONS = {'start', 'jobs'}
ACTIONS = {'search', 'explore', 'novel', 'local'}
JOB_HINT = re.compile(r'\b(python|java|javascript|react|backend|frontend|full.?stack|developer|desarrollador|programador|ingenier[oa]|enfermer[oa]|camarer[oa]|hotel|recepcionista|administrativ[oa]|contador|docente|profesor|diseñador|marketing|ventas|vendedor|chofer|conductor|mecanic[oa]|electricista|plomer[oa]|data|analista|qa|tester|devops|empleos? de|trabajo de|puesto de|vacantes? de)\b', re.I)

PRODUCTS = {'librería': r'\b(librer[ií]a|papeler[ií]a|[uú]tiles escolares|stationery)\b',
            'ferretería y herramientas': r'\b(ferreter[ií]a|herramientas?|destornilladores?|taladros?)\b',
            'teléfonos': r'\b(tel[eé]fonos?|celulares?|smartphones?|m[oó]viles?)\b',
            'ropa': r'\b(ropa|pantalones?|remeras?|camisetas?|indumentaria)\b',
            'calzado': r'\b(calzado|zapatillas?|zapatos?)\b',
            'electrónica': r'\b(electr[oó]nica|auriculares?|relojes? inteligentes?)\b'}

AMBIGUOUS = re.compile(r'^(?:no\s+s[eé]|ni\s+idea|algo|algo\s+(?:bueno|interesante|que\s+funcione)|lo\s+que\s+sea|depende|quiz[aá]s|tal\s+vez|puede\s+ser|mmm+|nose|i\s+don.t\s+know|not\s+sure|non\s+so|nie\s+wiem)[.!?\s]*$', re.I)

def ambiguity_streak(answers):
    count = 0
    for answer in reversed(answers):
        if AMBIGUOUS.fullmatch(answer.strip()):
            count += 1
        else:
            break
    return count

BASE = {'explore': 'Descubrir productos con potencial de reventa',
        'novel': 'Buscar novedades de productos para revender',
        'local': 'Buscar oportunidades comerciales locales para revender',
        'search': 'Investigar productos y oportunidades de reventa'}


def resolve(payload):
    if not isinstance(payload, dict):
        raise ValueError('invalid_payload')
    situation, action = payload.get('situation'), payload.get('action', 'search')
    if situation not in SITUATIONS or action not in ACTIONS:
        raise ValueError('unsupported_journey')
    message = str(payload.get('message') or '').strip()[:3000]
    answers = payload.get('answers') or []
    if not isinstance(answers, list) or len(answers) > 12 or any(not isinstance(x, str) for x in answers):
        raise ValueError('invalid_answers')
    answers = [a.strip()[:1000] for a in answers if a.strip()]
    latest = answers[-1] if answers else ''
    ambiguous_count = ambiguity_streak(answers)
    usable_answers = [a for a in answers if not AMBIGUOUS.fullmatch(a)]
    usable_latest = usable_answers[-1] if usable_answers else ''
    combined = ' '.join([message, *usable_answers])
    confirmed = payload.get('confirmed') is True
    market = ''  # Never infer a search restriction from publication/interface location.
    budget = ''  # A suggested UI budget is not a user-confirmed constraint.
    if situation == 'jobs':
        intent = 'find_recent_jobs' if action == 'novel' else 'find_local_jobs' if action == 'local' else 'find_jobs'
        role = next((a for a in reversed(usable_answers) if JOB_HINT.search(a)), '')
        if not role and JOB_HINT.search(message):
            role = message if len(message) < 140 else ''
        # A concrete free-text role can be accepted by the user even if not in the dictionary.
        if not role and usable_latest and not re.fullmatch(r'(cualquiera|lo que sea)', usable_latest, re.I):
            role = usable_latest
        objective = ('Buscar oportunidades laborales' + (' recientes' if action == 'novel' else '') +
                     (f' relacionadas con: {role}.' if role else '.'))
        question = '¿Qué tipo de trabajo o puesto estás buscando?' if not role else None
        title = f'Buscar empleo: {role}' if role else 'Buscar oportunidades laborales'
        search_type = 'Búsqueda laboral'
        category = role
        result = 'Vacantes verificables, requisitos y enlaces de postulación'
        missing = ['Tipo de trabajo o puesto'] if not role else []
        sufficient = bool(role)
    else:
        intent = {'explore': 'discover_resale_products', 'novel': 'discover_trending_products',
                  'local': 'discover_local_resale_opportunities', 'search': 'resale_research'}[action]
        category = next((name for name, pattern in PRODUCTS.items() if re.search(pattern, usable_latest, re.I)), '')
        if not category:
            category = next((name for name, pattern in PRODUCTS.items() if re.search(pattern, combined, re.I)), '')
        if not category and usable_latest and not re.fullmatch(r'(de todo|cualquiera|varios|distintas categor[ií]as|no s[eé])', usable_latest, re.I):
            # Unknown category is not an error: retain the user's own wording for validation.
            category = re.sub(r'^(?:de|para|sobre|quiero|busco)\s+', '', usable_latest, flags=re.I).strip()
        broad = bool(re.search(r'\b(de todo|cualquiera|varios|distintas categor[ií]as|sin preferencia)\b', usable_latest, re.I))
        objective = BASE[action] + (f' de {category}' if category else ' de distintas categorías') + '.'
        title = BASE[action] + (f': {category}' if category else '')
        search_type = {'explore': 'Descubrimiento de productos', 'novel': 'Novedades y tendencias',
                       'local': 'Oportunidades locales', 'search': 'Investigación comercial'}[action]
        result = 'Productos y oportunidades con fuentes verificables, sin duplicados'
        # Exploration can be broad; after the first reply, even unknown categories can be validated.
        sufficient = action != 'search' or bool(category) or broad
        question = ('¿Querés descubrir productos para revender, encontrar proveedores o comparar precios?'
                    if action == 'search' else '¿Tenés algún tipo de producto en mente o preferís explorar distintas categorías?')
        missing = ['Objetivo de la búsqueda'] if not sufficient else []
    # An ambiguous reply cannot turn a draft into a confirmed objective.
    if ambiguous_count and not (situation == 'start' and action != 'search' and not category):
        sufficient = bool(sufficient and usable_answers)
    state = 'CONFIRMED' if sufficient and confirmed else 'READY_TO_CONFIRM' if sufficient else 'NEEDS_CLARIFICATION'
    preview = {'task_title': title, 'search_type': search_type, 'search_market': market,
               'product_category': category, 'budget': budget, 'expected_result': result,
               'missing_required': missing}
    if ambiguous_count and not sufficient:
        question = ('¿Qué puesto u oficio te interesa? Podés indicar uno o un sector.' if situation == 'jobs'
                    else '¿Querés descubrir productos para revender, buscar proveedores o comparar precios?' if action == 'search'
                    else '¿Preferís explorar todas las categorías o tenés un producto específico en mente?')
    return {'ambiguity_count': ambiguous_count, 'needs_ai_interpretation': ambiguous_count >= 3 and not sufficient, 'state': state, 'domain': 'employment' if situation == 'jobs' else 'commerce',
            'intent': intent, 'objective': objective if sufficient else None,
            'question': question if not sufficient else None,
            'confirmation': f'{objective} ¿La tarea está lista o querés agregar algo más?' if state == 'READY_TO_CONFIRM' else None,
            'context': {'situation': situation, 'action': action}, 'task_preview': preview,
            'execution_allowed': state == 'CONFIRMED'}
