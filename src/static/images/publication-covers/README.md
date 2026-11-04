# Portadas reales DPIA

Las portadas se preparan manualmente; la navegación solo lee JavaScript y WebP
estáticos locales. No consulta MySQL ni el bucket para resolver portadas.

## Regeneración manual

Desde la raíz del proyecto, con el entorno de desarrollo activado:

```bash
python -m pip install -r requirements-dev.txt
python scripts/build_publication_covers.py
```

El script utiliza la configuración MySQL existente de `src/.env` en el servidor,
abre una transacción `READ ONLY` y ejecuta exclusivamente SELECT. No crea tablas,
no actualiza datos y no llama al scraper, Sheets, Base44 ni a la API DPIA.
Solo hace GET de imágenes HTTPS de `storage.googleapis.com/bucket_202404/`, sin
seguir redirecciones. No escribe en el bucket ni modifica los originales.
No se ejecuta automáticamente al iniciar Flask ni al navegar.

## Selección y estabilidad

- Solo publicaciones activas, categorías existentes y relaciones explícitas.
- Si la categoría directa contradice alguna relación activa de
  `categoriaPublicacion`, se excluye toda la publicación.
- Si no hay categoría directa, se utilizan las relaciones activas verificadas.
- Ámbitos mediante `ambitoCategoriaRelation` activo, sin inferir por nombre.
- Se normaliza el código de idioma (`It` → `it`, `in` → `en`), no los IDs.
- Se intentan las imágenes principales antes de las adicionales de todas las
  publicaciones candidatas; orden estable por ID de publicación y de multimedia.
- Se mantiene la fuente seleccionada anteriormente si sigue asociada a una
  publicación válida y la imagen sigue siendo accesible y decodificable.
- Se excluyen URLs externas, rutas relativas sin resolución explícita, redirecciones,
  archivos corruptos y fotos menores de 160 × 120 px. Hay límites de descarga y
  de píxeles. Las imágenes se recortan a 480 × 360 y codifican como WebP calidad 82.
- Las miniaturas se identifican por hash de su contenido. No se eliminan versiones
  anteriores automáticamente. Las descargas se comparten dentro de cada ejecución;
  la fuente se revalida en cada regeneración manual.

El manifiesto conserva `publication_id`, `category_id`, `source_url`, `source_kind`,
`media_id`, nombre de miniatura, hash y dimensiones. No contiene emails, tokens ni
credenciales. `catalog-reference.json` documenta los IDs y relaciones leídos.

## Contexto y respaldo

`manifest.json` incluye inventario global por idioma y variantes por ciudad.
La PWA usa la variante de la ciudad elegida, sin recurrir a fotos globales de otras
ciudades cuando falta una foto local. La pertenencia local se resuelve con IDs
postales directos y relaciones; solo sin IDs explícitos se considera el texto postal.

Prioridad: fotografía de categoría → fotografía de un ámbito relacionado (el que
se abrió) → degradado tipográfico. Si falla la carga de una miniatura, se intenta
el siguiente respaldo y nunca se muestra un icono de fábrica en estas tarjetas.
Los nombres visibles y los filtros siguen procediendo del catálogo habitual.

`publication-covers-map.js` es la copia de ejecución del manifiesto, generada por el
mismo script. No se edita manualmente. El mapa genérico anterior
`catalog-artwork-map.js` ya no se carga en la PWA.

## Verificación

```bash
python -m unittest discover -s tests -p 'test_publication_covers.py' -v
python -m unittest discover -s tests -p 'test_catalog_artwork.py' -v
python -m unittest discover -s tests -p 'test_catalog_ui.py' -v
```

Para navegador usar `CHROME_BIN` o instalar Chromium de Playwright. Las pruebas
usan fixtures locales e interceptan redes; no acceden a producción.

`coverage.json` enumera cobertura global y por ubicación, IDs sin foto, respaldos,
publicaciones excluidas y fuentes fallidas. Las cifras por ciudad se calculan sobre
el inventario completo de IDs, no solo sobre las categorías visibles en esa ciudad.
La selección prueba asociación y validez técnica; no evalúa automáticamente la
calidad editorial de una foto. No se usan imágenes genéricas ni generación IA.
