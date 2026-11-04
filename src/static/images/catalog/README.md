# Biblioteca local de ámbitos y categorías

Los seis WebP reutilizan recursos existentes del proyecto; no se descargaron
imágenes ni se generaron imágenes con IA. Tienen encuadre 4:3, 480 × 360 px,
calidad WebP 82 y un peso total aproximado de 37 KB. Se regeneran con
`python scripts/build_catalog_images.py` (Pillow, solo durante desarrollo).

| Archivo | Recurso original | Tema |
| --- | --- | --- |
| technology.webp | laptop.webp | Tecnología e informática |
| sport.webp | football.webp | Deporte y fútbol |
| audio.webp | headphones.webp | Audio y auriculares |
| footwear.webp | sneakers.webp | Calzado |
| furniture.webp | sofa.webp | Muebles |
| wearables.webp | watch.webp | Dispositivos vestibles |

`../../catalog-artwork-map.js` contiene asignaciones explícitas por idioma, tipo e
ID. `catalog-reference.json` conserva únicamente el catálogo público usado como
evidencia de IDs, nombres y relaciones: GET de ámbitos y categorías por `es`, `in`,
`pl` e `it`, consultados el 4 de noviembre de 2026. La clave de servicio no forma
parte de estos archivos. El idioma UI `en` corresponde al catálogo DPIA `in`.
La referencia no se carga durante la navegación.

Prioridad de categorías: imagen propia → respaldo del ámbito activo relacionado →
tarjeta tipográfica con iniciales, degradado y composición geométrica en CSS.
Sin ámbito activo, se consideran los ámbitos relacionados en el orden del catálogo.
Cada URL se intenta una sola vez por tarjeta; un error de carga avanza al siguiente
respaldo. Las imágenes usan exclusivamente rutas locales, alt vacío decorativo,
carga diferida y dimensiones explícitas. El texto accesible es el nombre original
de la tarjeta. Los nombres se insertan con textContent, nunca como HTML.

Para agregar una imagen: preparar un WebP temático, verificar ID/nombre/idioma y
relaciones en el catálogo real, actualizar la referencia y el mapa y ejecutar
las pruebas. No asignar por similitud de nombres ni asumir IDs equivalentes entre
idiomas. Un ID desconocido, nombre que cambió o tema sin imagen apropiada conserva
el diseño tipográfico. No se usan iconos de fábrica como respaldo en estos catálogos.

Las imágenes de publicaciones y productos de demostración mantienen su lógica.
