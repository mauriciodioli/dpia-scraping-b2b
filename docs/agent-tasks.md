# Administración de tareas configuradas

Se incorpora «Mis tareas (N)» a `agentContent`, antes de los controles existentes del agente. Las tarjetas usan el catálogo i18n español/inglés/polaco/italiano, elementos DOM con texto escapado, estados de carga y confirmación de eliminación.

## MVC y archivos

- `src/model/agent_tasks.py`: repositorio transaccional; refleja las tablas existentes sin DDL. Acceso a `agentes`, `agente_tareas`, `agente_programaciones`, `ae_agents`, `ae_schedules`; lectura opcional de `agente_ejecucion_tareas` y `ae_jobs`.
- `src/services/agent_tasks.py`: autorización de vínculos, reglas de estado, borrado lógico y coordinación de programaciones.
- `src/routes/agent_task_routes.py`: Blueprint/controlador HTTP; sesión, protección de origen y encabezado `X-DPIA-Action: manage-task`, errores JSON sin caché.
- `src/services/agent_configuration.py`: lectura compatible con tareas individuales pausadas o eliminadas. La edición explícita de configuración conserva el comportamiento previo de seleccionar/reactivar tareas.
- `src/app.py`: registro del Blueprint.
- `src/static/agent.js`, `styles.css`, `i18n.js` y `src/templates/index.html`: vista, traducciones y versiones de recursos.
- `tests/test_agent_tasks.py`, `tests/test_agent_tasks_ui.py`: regresiones aisladas; permanecen excluidas de Git conforme a la configuración actual.

## Endpoints

- `GET /api/agentes/{agent_id}/tareas`
- `PATCH /api/agentes/{agent_id}/tareas/{task_id}/activar`
- `PATCH /api/agentes/{agent_id}/tareas/{task_id}/pausar`
- `DELETE /api/agentes/{agent_id}/tareas/{task_id}`

Respuestas exitosas: `success`, `tasks`, `count`, `execution_available: false`. El servidor comprueba usuario activo, propietario, pertenencia y vínculos. Un bloqueo del usuario y de las filas serializa los cambios con la configuración existente. Los reintentos mantienen el estado final; repetir DELETE devuelve el listado sin la tarea eliminada.

## Relaciones y datos previos

`ae_agents.legacy_agent_id` identifica el motor propietario; `agente_tareas.ae_agent_id`, si está poblado, debe coincidir. Solo se modifican `ae_schedules` del propietario/agente con `legacy_task_id` igual a la tarea. No se asignan vínculos por inferencia ni se crean programaciones. Una programación original activa o una programación de motor sin tarea produce 409, pues cambiarla podría afectar a las demás tareas. Activar una tarea de un agente vinculado sin programación propia también produce 409 hasta completar sus vínculos existentes. Las tareas sin motor pueden administrar su habilitación local.

La activación conserva una próxima fecha futura o calcula la siguiente fecha DAILY/WEEKLY de su definición existente; una definición incompatible devuelve 409 con rollback. No se cambian los estados de pausa global del agente. El estado de la tarjeta expresa la habilitación de la tarea, sujeto a los controles globales del agente.

La última ejecución combina el dato original y `ae_jobs.started_at` por `legacy_task_id`, propietario y agente, si existe. Se muestran puntos únicamente cuando `agente_ejecucion_tareas` expone `tarea_id` y `puntos_consumidos` y hay datos; no se atribuye el presupuesto global a una tarea. Sin vínculo de programación propio se muestra el horario original como referencia y no se inventa una próxima ejecución.

## SQL adicional

Ninguno. Se reutiliza el patrón `_deleted_at` de la configuración del agente dentro del JSON `agente_tareas.parametros`. Una tarea eliminada queda deshabilitada, conserva su fila y no aparece en el contador. No se usa `habilitada = 0` como único indicador de borrado. No se ejecutaron migraciones ni se modificaron las cinco relaciones suministradas.

No se crean trabajos, ejecuciones ni cargos. No se modifican dispatcher, workers, scraper, historial ni mecanismos de puntos. Los trabajos ya existentes no se cancelan mediante estos endpoints.

## Validación

Pruebas de backend con SQLite aislado y navegador Chromium con HTTP simulado. Debe verificarse además contra una base MySQL de pruebas con las cinco relaciones ya aplicadas; no se accedió a producción.

Comprobaciones ejecutadas:

- `PYTHONPATH=src:tests python -m unittest test_agent_tasks test_agent_configuration test_agent_activation test_agent_pause test_agent_tasks_ui -q`: 34 pruebas correctas.
- `test_agent_ui`, `test_agent_activation_ui`, `test_agent_pause_ui`: otras 11 pruebas correctas en Chromium.
- `git diff --check`: correcto.


## Verificación de coordinación B2B ↔ Agent Engine (2026-11-12)

Esta sección actualiza el comportamiento de programación descrito anteriormente. Se encontraron cortes en la conexión: la activación creaba una programación general sin tarea; las tareas nuevas conservaban su horario solo en B2B; el dispatcher no propagaba el identificador de tarea.

Ahora la programación individual de `agente_tareas.parametros.schedule` se sincroniza mediante el endpoint firmado existente de activación, al crear/modificar una tarea vinculada y al activar una tarea que carece de programación propia. La activación inicial registra una programación por tarea. Se reutiliza la fila vinculada y se conservan las programaciones de las demás tareas. Una tarea nueva permanece pausada hasta su activación. No se ejecutó ninguna actualización masiva de datos existentes.

La relación es `agente_tareas.id` → `ae_schedules.legacy_task_id` → `ae_jobs.legacy_task_id`, con validación del agente y propietario. `Dispatcher.tick()` selecciona las programaciones habilitadas cuyo `next_run_at` UTC ha llegado; `_run_schedule()` comprueba la tarea, crea su trabajo y avanza su próxima fecha. Se conserva la idempotencia por programación y horario. La programación general histórica conocida de la activación PWA se deshabilita al establecer los vínculos individuales.

Prueba aislada con zona `Europe/Rome`:

| Tarea | Horario local | Instante UTC comprobado | Resultado |
| --- | --- | --- | --- |
| Productos nuevos | Lunes 09:00, activa | 2026-11-16 08:00 | Solo tarea 101 |
| Proveedores | Miércoles 10:00, pausada | 2026-11-18 09:00 | Sin trabajo para tarea 102 |
| Tendencias | Viernes 15:00, activa | 2026-11-20 14:00 | Solo tarea 103 |

Los trabajos conservan su identificador de tarea. Dos tareas al mismo horario crean dos trabajos distintos sin duplicarse al repetir el tick. Agregar/modificar una tarea conserva intactas las otras tres programaciones. A las 09:00 de Roma corresponden las 08:00 UTC en invierno y las 07:00 UTC en verano; se verificaron las transiciones de marzo y octubre de 2026. Se mantiene la política existente del motor de rechazar horas locales ambiguas o inexistentes.

Validación: 6 pruebas integrales de coordinación y 27 de configuración/activación/pausa B2B correctas. De 22 regresiones adicionales del motor pasan 21; falla la de deshabilitación de una programación tras revocar un cliente. Se reprodujo el mismo fallo con el código original de HEAD en una copia temporal, por lo que queda fuera de esta corrección. Una prueba antigua de tareas B2B también tiene una fixture incompatible: intenta agregar de nuevo `ae_agent_id`, ya presente en el modelo original. Las pruebas locales permanecen ignoradas por Git.

No se añadieron tablas ni se ejecutaron migraciones, tareas reales, proveedores pagos, despliegues o reinicios. La validación usa SQLite aislado y transporte HTTP local; queda pendiente comprobar los datos de una instalación MySQL desplegada. La interfaz de programación, presupuestos y scrapers no se modificaron.
