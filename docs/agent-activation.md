# Activación PWA → motor

Desplegar ambos repositorios. Configurar el mismo `PWA_ACTIVATION_SECRET` aleatorio en ambos servicios y `AGENTS_INTERNAL_URL` (origen interno del motor, sin ruta) en ms202611sb2b. Usar red privada o HTTPS. Sin estas variables, la activación falla cerrada. No requiere migración ni crea tablas al iniciar.

El POST `/api/agente/activar` acepta solamente `expected_revision`, requiere sesión propietaria y las protecciones de origen/acción existentes. La operación interna firmada HMAC vence a los 60 segundos; valida que el propietario siga activo. La unicidad de `ae_agents.legacy_agent_id` y el bloqueo del propietario serializan creación y reintentos. Una repetición con configuración o propietario distintos falla con conflicto. El vínculo inverso queda en `agentes.configuracion.engine_binding`, después de la confirmación. Si se pierde la respuesta o falla ese guardado, repetir recupera el mismo agente remoto.

Compatibilidad: Productos nuevos con un ámbito y una categoría; diario, semanal y dos días por semana (WEEKLY con días ISO). Otras tareas y avisos activos se rechazan antes de escribir. Los parámetros de tareas y programación deben coincidir con la configuración guardada. Horarios y preferencias de presupuesto se preservan en la auditoría remota, sin crear programaciones ejecutables. No se crean jobs, reservas, búsquedas ni consumos. Pausa y edición de agentes activados quedan fuera de este cambio.

Pruebas aisladas: `PYTHONPATH=src:tests python -m unittest test_agent_activation -q` en la PWA y `PYTHONPATH=src:tests python -m unittest test_pwa_activation -q` en el motor.
