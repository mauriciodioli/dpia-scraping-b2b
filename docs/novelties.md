# Novedades en la PWA

El botón Novedades completa ámbito y categoría del catálogo seleccionado y la ciudad actual. Propone un pedido editable; abrir esta pantalla no llama a proveedores.

Preparar consulta permite revisar el resumen. Buscar novedades utiliza el prompt genérico y valida la respuesta estructurada de OpenAI antes de enviar la búsqueda al marketplace elegido mediante la integración DPIA existente. Los candidatos IA se identifican como no verificados; los productos reales se muestran por separado.

Se admite un marketplace externo por operación. El contador reserva una ejecución antes de preparar la búsqueda y consume al iniciar el trabajo. Un error de preparación o una pregunta aclaratoria libera la reserva. La preparación se conserva en el registro existente para evitar repetir OpenAI al reintentar la misma operación. Un estado de inicio incierto mantiene la reserva para reconciliación.

Requiere la configuración existente de proveedores habilitados, OpenAI y la clave del Scrapeador. No agrega tablas ni cambia endpoints externos. Las pruebas locales simulan OpenAI y DPIA; no ejecutan Apify.
