# Administración de tareas configuradas

Se incorpora «Mis tareas (N)» a `agentContent`, antes de los controles existentes del agente. Las tarjetas usan el catálogo i18n español/inglés/polaco/italiano, elementos DOM con texto escapado, estados de carga y confirmación de eliminación.

## MVC y archivos

- `src/model/agent_tasks.py`: repositorio transaccional; refleja las tablas existentes sin DDL. Acceso a `agentes`, `agente_tareas`, `agente_programaciones`, `ae_agents`, `ae_schedules`; lectura opcional de `agente_ejecucion_tareas` y `ae_jobs`.
- `src/services/agent_tasks.py`: autorización de vínculos, reglas de estado, borrado lógico y coordinación de programaciones.
- `src/routes/agent_task_routes.py`: Blueprint/controlador HTTP; sesión, protección de origen y encabezado `X-DPIA-Action: manage-task`, errores JSON sin caché.
- `src/services/agent_configuration.py`: lectura compatible con tareas individuales pausadas o eliminadas. La edición explícita de configuración conserva el comportamiento previo de seleccionar/reactivar tareas.
- `src/app.py`: registro del Blueprint.
- `src/static/agent.js`, `styles.css`, `i18n.js` y `src/templates/index.html`: vista, traducciones y versiones de recursos.
- `tests/test_agent_tasks.py`, `tests/test_agent_tasks_ui.py`: regresiones aisladas; `.gitignore` permite versionarlas.

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
