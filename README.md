# DPIA — demo visual Flask (v3)

## Estructura del proyecto

```
.
├── Dockerfile
├── .dockerignore
├── .github/workflows/aws.yml   # CI/CD: build + push a Docker Hub y deploy a EC2
└── src/
    ├── app.py                  # Punto de entrada (factory create_app)
    ├── config.py               # Configuración leída desde .env
    ├── .env                    # Variables de entorno locales (no se commitea)
    ├── requirements.txt
    ├── model/                  # Modelos SQLAlchemy + schemas Marshmallow
    ├── controllers/            # Traducen request/response HTTP, llaman a services
    ├── services/                # Lógica de negocio (p.ej. verificación Google)
    ├── routes/                  # Blueprints (definen los endpoints)
    ├── utils/                   # Utilidades compartidas (instancia db, etc.)
    ├── static/
    └── templates/
```

## Correr en local (sin Docker)

```powershell
cd src
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" app.py
```

Abrir http://127.0.0.1:8100 (puerto configurable con `PORT` en `src/.env`).

## Correr con Docker

```powershell
docker build -t dpia .
docker run -p 8100:8100 --env-file src/.env dpia
```

Abrir http://127.0.0.1:8100

Incluye onboarding país/ciudad/intereses (Industria incluida), inicio, categorías, mapa OpenStreetMap aproximado, formulario de consulta con foto/video y grabación de audio mediante navegador, y pantalla de puntos. El mapa requiere Internet. El micrófono requiere permiso y localhost o HTTPS. No hay scraping, pagos, autenticación, transcripción, interpretación multimedia ni API real conectados. Los productos, precios y puntos son ficticios. No altera los microservicios DPIA existentes.


## V5 — Diseño adaptable
- PC (más de 1120 px): diseño de ancho completo, 4 columnas y navegación superior.
- Tablet (760–1120 px): 3 columnas y navegación superior.
- Celular (menos de 760 px): diseño original con carruseles y navegación inferior.
- No se modificó la lógica de JavaScript, los endpoints ni la API de producción.


## V8 Branding
- Reemplazadas las estrellas decorativas por el isotipo DPIA oficial del paquete de logos.
- Consultar muestra el logotipo correcto según el tema claro/oscuro.
- Botones de regreso con contraste visible en tema oscuro.
- Conservados endpoints, JS, i18n, navegación y favicon.


## V9 — Italiano
Aggiunto IT al selettore e tradotte le stringhe UI in italiano, mantenendo ES/EN/PL, temi, branding e funzionalità.

## Etapa 1 — Catálogos DPIA

Los intereses (ámbitos) y las categorías ahora proceden de la API DPIA. Los productos,
publicaciones, precios y puntos siguen siendo de demostración. Esta etapa no ejecuta
scraping, pagos ni cambios en autenticación, Base44, Sheets o MySQL.

### Configuración y ejecución local

Mantener las variables existentes de `src/.env` y agregar, si falta:

```dotenv
SCRAPEADOR_SERVICE_KEY=<clave con permiso scraper:read>
# Opcionales, en segundos:
DPIA_CONNECT_TIMEOUT=3.05
DPIA_READ_TIMEOUT=10
```

`src/config.py` carga primero `src/.env` y también admite `/src/.env` en Docker.
Las variables ya presentes en el entorno tienen prioridad. La clave permanece en
Flask; nunca se incorpora al HTML o JavaScript. La URL base es fija:
`https://api.dpia.site/api/scraper/v1`. Reiniciar Flask tras cambiar configuración.

Desde la raíz, usando Python 3.12 o posterior:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r src/requirements.txt
.venv\Scripts\python.exe src/app.py
```

Abrir `http://127.0.0.1:8301` (o el `PORT` existente). Elegir país, ciudad e intereses;
comprobar las categorías y cambiar entre ES/EN/PL/IT. En DevTools, las peticiones
de catálogo deben ir exclusivamente a las rutas internas, sin encabezado Bearer.
Las imágenes siguen siendo archivos locales existentes, con `industry.svg` para
nombres sin una imagen asociada. El inicio muestra únicamente los ámbitos seleccionados. Al pulsar uno aparecen
solo sus categorías para la ciudad y el idioma elegidos. Al elegir una categoría
se abre la consulta conservando ese ámbito, incluso si pertenece a varios.

### Contrato comprobado

Verificado mediante GET contra producción y lectura del código fuente de la API
el 3 de noviembre de 2026:
[servicio de catálogos](https://github.com/mauriciodioli/dpia-popup-service/blob/master/src/services/scraper_catalogs.py)
y [rutas existentes](https://github.com/mauriciodioli/dpia-popup-service/blob/master/src/controllers/conexionesSheet/api.py).
No se modificó ese repositorio.

| Ruta interna Flask | GET remoto | Filtros opcionales |
| --- | --- | --- |
| `/api/catalogos/ambitos` | `/catalogos/ambitos` | `idioma`, `ambito_id`, `codigo_postal_id` |
| `/api/catalogos/categorias` | `/catalogos/categorias` | Los anteriores y `categoria_id` |

Los IDs deben ser enteros entre 1 y 2147483647. Se rechazan filtros desconocidos
o repetidos. Las rutas individuales permiten esos filtros; el frontend utiliza ahora
la ruta de ubicación con los IDs reales de `codigo_postal`. DPIA usa `in` para
inglés: Flask convierte `en` a `in`. Los nombres se muestran como los devuelve la API,
sin traducirlos con el diccionario de la demo.

```json
{"success":true,"total":1,"ambitos":[{"ambito_id":2,"idioma":"es","nombre":"Tecnologia"}]}
```

```json
{"success":true,"total":1,"categorias":[{"categoria_id":19,"categoria_general_id":2,"ambito_id":2,"ambito_ids":[2],"idioma":"es","nombre":"Teléfonos"}]}
```

`ambito_id` y `categoria_general_id` de una categoría pueden ser `null`;
`ambito_ids` puede contener cero, uno o varios ámbitos. `idioma` puede ser `null`.
Una respuesta vacía es HTTP 200 con lista vacía. Flask devuelve 400 para filtros
inválidos, 503 si falta la clave, 504 para timeout y 502 para errores HTTP remotos,
conexión o JSON/contrato inválido. Los 401/403 remotos se presentan como fallo del
servicio de catálogos, sin alterar la sesión del usuario. No se reenvían mensajes
de error remotos ni se siguen redirecciones con la clave.

Los intereses se guardan por ID e idioma en `dpia-demo`. Las preferencias antiguas
se recuperan por coincidencia de nombre normalizado; los nombres ficticios sin
equivalencia real deben elegirse otra vez. No se presume equivalencia entre IDs de
distintos idiomas. La pantalla permite continuar sin intereses cuando el catálogo
está vacío o falla, y ofrece reintento. Con datos disponibles requiere hasta tres
selecciones, según la cantidad de ámbitos recibida.

### Pruebas aisladas

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
git diff --check
```

Las pruebas de navegador usan Chrome instalado en Windows. Para otro ejecutable,
definir `CHROME_BIN`; si Chrome no existe, instalar el Chromium de Playwright con
`.venv\Scripts\python.exe -m playwright install chromium`.

La suite usa respuestas simuladas, configuración Flask de prueba y SQLite en memoria
para comprobar el registro de rutas. No lee claves reales, conecta a MySQL, ejecuta
scraping ni consume Apify. Verifica Bearer, filtros, errores, timeouts, importación
sin red, protección de secretos y navegación móvil/escritorio, cambio de idioma,
persistencia, migración, reintentos y respuestas atrasadas.

## Login Google y usuarios

El login existente con Google Identity Services valida el ID token en el servidor
y guarda el usuario en la tabla `usuarios` antes de establecer la sesión. Se busca
primero por `google_id` (el `sub` estable de Google); los accesos posteriores
actualizan `google_email`, `google_picture` y `auth_provider` sin duplicar usuarios.
Los usuarios nuevos se crean activos, con rol `regular` y sin contraseña ni tokens
OAuth almacenados. No se cambian las tablas ni se ejecutan migraciones al arrancar.

Las cuentas existentes se vinculan por email solo si Google es la autoridad de esa
dirección (Gmail o Workspace con `hd`), sin cambiar contraseña ni rol. Se rechazan
cuentas deshabilitadas y conflictos con otra identidad Google. Los fallos de base de
datos hacen rollback y no abren sesión.

Configurar en `src/.env`, conservando las demás variables existentes:

```dotenv
GOOGLE_OAUTH_CREDENTIAL='utils/google_oauth_credentials.json'
GOOGLE_CLIENT_ID='<client_id del objeto web del JSON>'
FLASK_SECRET_KEY='<clave aleatoria persistente del servidor>'
```

La ruta relativa se resuelve respecto de `src`, tanto en Windows como en Docker
(`/src/utils/google_oauth_credentials.json`). Si falta `GOOGLE_CLIENT_ID`, se lee
del JSON. Solo el Client ID público se entrega al navegador. El flujo actual de
ID token no requiere enviar ni usar el Client Secret en el navegador. El JSON está
excluido de Git y Docker; en producción debe inyectarse como archivo del servidor.

En el cliente OAuth correspondiente de Google Cloud, agregar estos **orígenes
JavaScript autorizados**:

- `https://s.dpia.site`
- `http://localhost:8301` para pruebas locales (adaptar al `PORT` utilizado).
- `http://127.0.0.1:8301` si se usa esa dirección local.

Conservar los orígenes anteriores para no afectar otros servicios. El JSON recibido
solo enumeraba `https://dpia.site` y `http://localhost:5001`: editar el archivo local
no actualiza la configuración en Google Cloud. El flujo actual usa un callback
JavaScript y `POST /api/auth/google`; no requiere agregar una ruta OAuth de redirect.
Ver [configuración oficial de Google](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid).

Reiniciar Flask tras corregir `.env`, pulsar **Ingresar** y acceder con Google. El
email debe aparecer en la cabecera; `GET /api/auth/me` debe devolver
`authenticated: true`. El registro se guarda en la base MySQL configurada por la
aplicación. Volver a ingresar debe reutilizar el mismo usuario. La suite de pruebas
de login simula la verificación Google y persiste únicamente en SQLite en memoria;
no crea usuarios de prueba en producción.

## Modelos compartidos y recarga de configuración

Los modelos usan el paquete `model` y las instancias únicas `db` y `ma` de
`utils.db`, inicializadas por la factory Flask. Los módulos adicionales quedan
disponibles para importación sin activar scraping, Sheets o chats ni crear tablas
en el arranque. El modelo `Usuario` mantiene los campos Google y la serialización
excluye contraseñas y tokens. La contraseña se mapea al tipo binario existente.

El helper de cifrado de mensajes utiliza `ENCRYPTION_KEY` de la configuración o
del entorno, con las mismas rutas locales/Docker de `.env`. Para usar ese helper
se debe suministrar una clave Fernet persistente; no se generan claves temporales
ni se imprimen claves en logs. No cambiar una clave existente sin un procedimiento
de migración para los mensajes cifrados con ella.

El workflow `aws.yml` copia `/home/ubuntu/.env` y las credenciales al contenedor,
ejecuta `docker restart` y verifica `/api/auth/config` hasta un máximo de 30 intentos.
El workflow falla si falta el Client ID o la aplicación no queda disponible.
Esto recarga el archivo mediante `load_dotenv` al reiniciar Python; los valores
inyectados como variables de entorno del contenedor siguen teniendo prioridad.
Si se cambian variables suministradas mediante `docker run --env-file`, hace falta
recrear el contenedor para actualizarlas; un reinicio por sí solo no las reemplaza.

## Ciudades y catálogos por ubicación

El selector de ciudad usa ahora la tabla existente `codigo_postal` mediante
`model.codigoPostal.CodigoPostal`, agrupando ciudades del país elegido. Se retiró
la lista fija de ciudades del JavaScript. Solo se hacen consultas de lectura a esa
tabla; las relaciones y los catálogos siguen siendo responsabilidad de la API DPIA.

- `GET /api/catalogos/ciudades?pais=Italia`: ciudades y sus IDs postales reales.
- `GET /api/catalogos/ubicacion?pais=Italia&ciudad=Spoleto&idioma=es`: ámbitos y
  categorías de todos los códigos postales asociados a esa ciudad, sin duplicados.

El endpoint de ubicación resuelve los IDs en `codigo_postal` y consulta la API con
`codigo_postal_id` e `idioma` para cada uno, con un máximo de cuatro consultas HTTP
simultáneas. No infiere IDs a partir del texto postal ni limita una ciudad a su
primer código. La selección de país, ciudad y lenguaje delimita el catálogo; al
cambiar la ciudad se invalida la respuesta anterior. Sin asociaciones se muestran
listas vacías; ante errores se permite reintentar, sin recurrir al catálogo global.
Los endpoints individuales `/ambitos` y `/categorias` mantienen su contrato previo.

Comprobado con consultas reales de lectura: Spoleto tiene 11 IDs postales asociados.
En español, la API devolvió un ámbito y cero categorías para esa ubicación al
verificar la integración. La interfaz conserva ese resultado sin inventar
categorías ni sustituirlas por las de otras ciudades o idiomas.

## Consultas, novedades y generación con OpenAI

La pantalla Consultar conserva tres etapas: pedido editable, resumen legible para
revisar y generación mediante instrucciones privadas de Flask. Permite seleccionar
un ámbito, una categoría relacionada y el código postal real dentro de la ciudad.
Novedades conserva ese contexto y cambia la intención a buscar candidatos novedosos.
Editar la selección o el pedido invalida el resumen y exige prepararlo nuevamente.

- `POST /api/consultas/preparar`: valida la sesión activa, resuelve el usuario desde
  MySQL y comprueba país/ciudad/código postal y las relaciones del catálogo DPIA.
  Devuelve el resumen y el contexto, sin instrucciones internas ni credenciales.
- `POST /api/consultas/generar`: vuelve a verificar el contexto y llama a OpenAI
  Responses con un JSON Schema estricto para `dpia.results.v2`. Devuelve `result`
  y `rows`, un mapeo a las columnas del Sheet de referencia. No escribe en Sheets.

La implementación utiliza la [documentación oficial de Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
No hay llamadas OpenAI al importar módulos. No se reintentan automáticamente las
generaciones, y el botón evita envíos simultáneos desde la misma pantalla.
La respuesta se valida también en Flask: contexto, país/moneda, cantidad de 5–10
candidatos, ausencia de duplicados y coherencia de las aclaraciones. Una aclaración
requiere `needs_clarification: true`, pregunta no vacía e `items: []`.

Configurar tanto en `src/.env` local como en `/home/ubuntu/.env` del servidor:

```dotenv
OPENAI_API_KEY='<clave API de tu proyecto OpenAI>'
OPENAI_MODEL='gpt-4o-mini'
```

La clave se configura exclusivamente en el servidor, nunca en JavaScript ni en Git.
El modelo es configurable y debe admitir Responses y Structured Outputs. Se agregó
la variable local vacía para completarla sin compartirla por chat. Reiniciar Flask
tras configurar las variables; el despliegue existente reinicia el contenedor tras
copiar el `.env`. La generación se habilita únicamente cuando existe una clave.

El país determina la moneda y el país de envío predeterminados: Argentina ARS/AR,
Uruguay UYU/UY, España EUR/ES, Italia EUR/IT, Polonia PLN/PL y México MXN/MX.
El ID de usuario proviene de la sesión, nunca de un campo enviado por el navegador.
El prompt privado se construye desde `services/query_preparation.py`; el esquema,
la llamada OpenAI y la validación están en `services/result_generation.py`.

Esta etapa genera candidatos y planes de búsqueda, no verifica marketplaces.
Por eso precios, márgenes, fuentes e imágenes se mantienen en `N/D` sin evidencia
externa; `validado`, `pagoOnline` y `botonCompra` son `false`, y el estado es
`CANDIDATO`. Se pueden descargar los resultados como JSON. No se envía el prompt
al scraper: el JSON es la entrada para una etapa posterior de scraping a través de
los endpoints DPIA existentes. No se ejecuta Apify, no se crean publicaciones ni
se modifica la lógica de créditos o pagos. Los adjuntos aún no se interpretan:
esta generación requiere texto y muestra un aviso si se intenta enviar archivos.


## Publicaciones locales

La pestaña Local conserva la navegación inferior y permite plegar el mapa. Debajo
muestra publicaciones activas reales de todos los códigos postales de la ciudad
seleccionada, en páginas de 24 mediante `GET /api/publicaciones/locales?pais=…&ciudad=…&offset=0`.
Se consultan `publicacion.codigo_postal_id`, `publicacionCodigoPostal` y, para filas
antiguas sin asociaciones explícitas, el texto exacto de `publicacion.codigoPostal`.
El código postal se utiliza internamente y no se muestra en las tarjetas. No se
modifica ninguna publicación ni se crean tablas al arrancar. La columna
`codigo_postal_id` corresponde al esquema aportado de la base existente.
El mapa conserva su visor integrado de OpenStreetMap dentro de un acordeón
que permite plegarlo sin salir de Local.

Al elegir una categoría y entrar en Local se conserva su `categoria_id`: el listado
combina esa categoría con todos los códigos postales de la ciudad, también al
cargar más páginas. Si no hay coincidencias se muestra el estado vacío.
