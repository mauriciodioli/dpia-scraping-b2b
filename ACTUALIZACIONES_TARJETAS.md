# Historial de agentes: fecha de actualización automática

En `src/static/query-history.js` se agrega el indicador **Actualizado automáticamente** a tarjetas de Agents, exclusivamente cuando `/api/consultas/historial/agentes` entrega `last_checked_at` válido. También aparece en el detalle. Se traduce a ES/EN/PL/IT. No se inventan fechas y las tarjetas manuales permanecen intactas.

**Dependencia obligatoria:** desplegar primero la versión complementaria de Agents que agrega `last_checked_at` a `/api/agents/v1/internal/pwa-history` usando `ae_schedule_current`. Esta tabla requiere la migración `docs/SQL_SCHEDULE_CURRENT.sql` del paquete Agents recurrente previo.

**Límite:** la fecha de actualización aparece únicamente en resultados programados que tienen un registro en `ae_schedule_current`. Si la ejecución falla, se conserva la fecha de la última comprobación exitosa. El backend conserva un solo resultado vigente por programación y filtra versiones anteriores del historial; los trabajos técnicos siguen en la base de datos.
