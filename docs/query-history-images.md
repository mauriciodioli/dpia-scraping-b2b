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

Cada producto Amazon ofrece **Preparar imágenes** y filtros de precio, rating y
reseñas. La evaluación individual replica las reglas del Scrapeador: si no hay
rating interpretable, se permite precio positivo sin exigir reseñas. Si hay rating,
se exigen los umbrales elegidos (por defecto 4.4 y 50). Esta acción individual no
aplica un Top-3 global a todos los productos.

Flask obtiene ASIN/dominio del resultado original persistido y llama a
`POST /imagenes/asin` con la clave privada y `scraper:write`, únicamente tras el
clic. Conserva hasta seis URLs reales: imagen principal más galería. Los resultados
se guardan en `resultado_json` de la operación existente. Lecturas posteriores
reutilizan la galería; peticiones inciertas quedan pendientes sin reenvío automático.
La preparación es una etapa de la operación y no altera su contador.

Después se puede **Guardar publicación** confirmando título, descripción, moneda
y selección de fotos. Se conserva el precio original positivo, sin margen ni precio
sugerido inventado. El guardado transaccional crea publicación, imágenes y relaciones
con los IDs de catálogo y postal ya seleccionados. Un marcador en la misma
transacción evita publicaciones duplicadas y resurrección tras eliminar una.

La publicación confirmada aparece en Mi perfil → Mis publicaciones y en las
consultas locales correspondientes. La eliminación individual usa el endpoint PWA
ya implementado y respeta sus comprobaciones de propiedad y dependencias.

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
