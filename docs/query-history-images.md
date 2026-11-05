# Historial, imágenes y publicaciones

La notificación global se oculta al pulsarla. Consultar un resultado guardado no
vuelve a mostrarla. Una nueva ejecución genera su propia notificación.

## Consultar → Historial

El selector permite dos orígenes, con sus contratos reales:

- **Mis búsquedas de la PWA**: `GET /api/consultas/historial` lista únicamente
  operaciones del usuario de sesión desde las tablas PWA existentes. Seleccionar
  una consulta recupera `GET /api/consultas/operaciones/<id>` sin repetir scraping.
- **API DPIA · Trabajos del Scrapeador**: Flask consulta `/auth/check` y comprueba
  que el usuario de sesión sea el titular de `SCRAPEADOR_SERVICE_KEY`. Después
  consulta `GET /trabajos?lugar=...` y `GET /archivos/<nombre>`. La API conserva su
  autorización adicional de administrador para recursos compartidos. Otros usuarios
  PWA no heredan ese acceso por utilizar la misma conexión del servidor.

`ArchivosCargados` usa los identificadores reales que corresponden a cada origen.
El contrato `/trabajos` revisado devuelve nombres de JSON, no UUID de trabajos
privados Base44. No se generan UUID falsos ni se envían IDs PWA a rutas Base44.

## Imágenes de resultados PWA

Las nuevas búsquedas Amazon iniciadas desde el modal de candidatos conservan
`POST /api/consultas/scraping-directo` y envían `image_pipeline: "base44"`.
Solo esa combinación cambia el despacho remoto a `POST /base44/scraping`, con
una clave estable derivada de la operación PWA. La búsqueda directa tradicional,
Novedades y los otros marketplaces conservan su transporte. La reserva de crédito
se realiza antes de enviar; se conserva el trabajo remoto real en `resultado_json`.

Al preparar imágenes, Flask valida sesión, propiedad, filtros y elegibilidad.
Consulta el trabajo mediante `GET /base44/trabajos/<trabajo_id>` y toma el
`producto_id` original, identificado por ASIN y dominio originales coincidentes
sin ambigüedad. No genera IDs remotos ni los deduce de posiciones o títulos.
Los resultados antiguos sin referencias Base44 se rechazan con 409 y no se reinician.
Las galerías antiguas ya completadas siguen siendo reutilizables.

`POST /api/consultas/operaciones/<id>/imagenes` registra una etapa `pending` en
`resultado_json/image_stages`: propietario, producto, IDs remotos, filtros,
diagnósticos, clave de idempotencia, fechas y lease. No requiere migraciones ni
modifica el crédito de la operación ya consumida. La preparación de imágenes
conserva la política existente: no descuenta un punto adicional.

El ejecutor iniciado por `python app.py` (entrada actual del contenedor) revisa
la cola persistente cada cinco segundos. La memoria del thread no contiene la
cola: al reiniciar se recuperan las etapas guardadas, con leases transaccionales
entre procesos. Solo procesa etapas explícitamente encoladas; no inicia búsquedas
ni trabajos antiguos. No se inicia al importar el módulo ni en modo TESTING.
Si se cambia la entrada del contenedor a WSGI deberá iniciarse explícitamente el
mismo ejecutor; no se modifica aquí el despliegue.

El worker consulta primero el trabajo original. Si falta la galería y aún no
se envió la preparación, persiste la intención y llama a `POST /base44/imagenes`
con `trabajo_id`, `productos: [{producto_id}]` e `idempotency_key`. Después de un
envío incierto, solo reconcilia con GET: no repite automáticamente la operación
pagada. Si un proceso cae después de registrar la intención y antes del POST,
la etapa permanece pendiente de verificación; no se puede distinguir esa ventana
de un envío cuyo resultado se perdió sin evidencia adicional del proveedor.

Estados: `pending` sin confirmación, `running` ante ocupación remota explícita,
`complete` con URLs reales y `failed` ante rechazo o fallo definitivo. Un 409
genérico no demuestra que haya ejecución. La API aplica además sus propios filtros;
si descarta el producto, la PWA lo informa aunque superara sus filtros locales.
La API actual no recibe los filtros personalizados de este formulario.

La consulta de estado usa GET en la misma ruta con `product_index`. El listado
`GET /api/consultas/imagenes/seguimiento` devuelve solo preparaciones del usuario
actual; no expone claves de idempotencia ni tokens de leases. La PWA consulta este
estado local cada cinco segundos cuando está visible, permite cerrar el modal y
recupera el seguimiento tras recargar. La finalización muestra un aviso dentro de
la PWA, sin push ni permisos del navegador. Se conservan hasta seis URLs válidas,
sin duplicados, y la selección de fotos se recuerda localmente por usuario/producto.

El guardado mantiene el endpoint de publicación y su transacción original:
requiere etapa completa, precio original positivo y selección de una a seis
imágenes preparadas. No publica automáticamente ni llama a la publicación Base44.

## Imágenes de trabajos del Scrapeador

**Preparar imágenes del trabajo** usa el contrato ya existente
`POST /scraping/imagenes`: `sheet_name`, `nombre_archivo`, `archivo_base` y filtros.
Recupera la selección real de `tablaB`, con el filtrado y Top-3 originales.
Este es el flujo legado que lee Sheets y escribe sus resultados/relaciones JSON;
no se cambia su implementación ni se llama al endpoint de publicación de Sheets.
Leer el historial no ejecuta esta etapa automáticamente.

## Verificación

`test_query_history_images.py`, `test_scraper_history_api.py` y
`test_query_history_ui.py` cubren propiedad, contratos, filtros, galerías, reservas
inciertas, publicación idempotente, rollback, moneda explícita y notificación consumida.
Las pruebas usan fixtures y HTTP simulado. No se ejecutó Apify, imágenes reales ni
publicaciones reales. No se crearon ni alteraron tablas o endpoints del Scrapeador.

### Regresión del adaptador Base44

`test_base44_dispatch.py`, `test_base44_images.py` y `test_base44_images_ui.py`
cubren el despacho opt-in, persistencia, leases, propiedad, filtros, rechazo de
legados, galerías, timeout, recuperación sin nuevo POST, modal cerrado, recarga,
aviso y selección/publicación explícita. Los proveedores se simulan; no se llama
al flujo activo `/imagenes/asin` ni se ejecuta scraping pagado.
