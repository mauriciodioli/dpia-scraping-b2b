# Scraping directo desde Consultar

Para texto sin adjuntos en modo buscar, seleccionar un único marketplace y confirmar Iniciar búsqueda. Se envía POST /api/consultas/scraping-directo sin invocar OpenAI. El indicador global permite volver a Consultar y ver los productos reales devueltos por DPIA. Navegar entre pantallas mantiene la petición y el indicador; recargar o cerrar la pestaña no tiene recuperación implementada todavía.

## Persistencia MySQL

Se usan exclusivamente las tablas nuevas creadas manualmente por el usuario:
`pwa_scraping_cupos` y `pwa_scraping_operaciones`. El servicio `MySQLScrapingQuota`
se registra en Flask y no crea tablas. No usa archivos ni SQLite.

Las reservas y las transiciones bloquean la fila de cupo del usuario. Un UUID
repetido con el mismo pedido devuelve la operación existente; si cambia el pedido
o el usuario, se rechaza. Los resultados terminales se reutilizan sin proveedor.
Las operaciones pendientes conservan la reserva; la consulta de estado lee MySQL,
no inventa un endpoint de seguimiento de Apify.

El indicador conserva la petición al navegar entre pantallas. Tras recargar,
Puntos muestra operaciones para recuperar sus resultados desde Consultar.

## Recarga de desarrollo

Con Flask en desarrollo (`DEBUG=True`), configurar en el entorno:

```
ENABLE_TEST_SCRAPING_CREDITS=true
```

Reiniciar Flask, iniciar sesión y entrar a Puntos. “Agregar 6 ejecuciones de prueba”
aumenta el cupo del usuario actual en MySQL. Con DEBUG desactivado o sin esta
opción, el botón está oculto y el endpoint rechaza la recarga.

Agregar cupo no activa proveedores. `LIVE_PROVIDER_CALLS_ENABLED` conserva su
configuración previa; ninguna prueba real se ejecuta automáticamente.

## Verificación sin proveedores

PYTHONPATH=src:tests python -m unittest discover -s tests -p 'test_direct_scraping.py'

Las pruebas verifican la exclusión de OpenAI, texto y marketplace explícitos, resultados reales simulados y bloqueo antes del despacho cuando falta persistencia.
