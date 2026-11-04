# Publicaciones propias y eliminación individual

Al pulsar el usuario autenticado en la cabecera se abre Mi perfil → Mis publicaciones.
Cerrar sesión sigue disponible dentro del perfil. El listado proviene de MySQL;
no incluye candidatos de OpenAI ni resultados de scraping sin publicación guardada.

- `GET /api/publicaciones/mias?offset=0`: lista hasta 24 publicaciones del usuario de sesión.
- `DELETE /api/publicaciones/<id>`: elimina una publicación del usuario de sesión.
  Requiere cabecera `X-DPIA-Action: delete-publication` y confirmación explícita en la UI.

El servidor verifica usuario activo, propiedad y dependencias. El ID y propietario
no se toman de un cuerpo enviado por el navegador. Una publicación inexistente o
ajena devuelve 404. Las referencias externas a las asociaciones permitidas
(pedidos, popups, chats, trabajos, etc.) bloquean la eliminación con 409.
Los fallos SQL revierten la transacción y se comunican sin detalles de conexión.

Solo se eliminan la publicación y sus asociaciones de categoría, ámbito de usuario,
postal, ubicación, estados y medios. Se conservan registros de imágenes/videos y
sus URLs; no se accede a buckets ni se modifican catálogos, trabajos o Sheets.
La detección usa columnas conocidas y claves foráneas del esquema real. Referencias
no declaradas mediante FK ni mediante `publicacion_id`, `id_publicacion` o
`publication_id` deben incorporarse explícitamente antes de permitir su eliminación.

El controlador conserva los helpers aportados; se corrigieron imports a `model`
y `utils.db`. El helper heredado de creación solo admite el modo de base de datos
por defecto y ya no importa ni llama a Sheets. No se exponen rutas de creación o
edición mediante esos helpers. El flujo de imágenes/publicación desde los resultados directos está documentado
en [historial e imágenes](query-history-images.md).

Pruebas locales: `test_publication_deletion.py` verifica propiedad, dependencias,
medios compartidos, rollback y listado privado con fixtures aislados.
`test_publication_profile_ui.py` verifica confirmación/cancelación, DELETE, errores
y logout con HTTP simulado. No se eliminaron publicaciones reales para probar.
