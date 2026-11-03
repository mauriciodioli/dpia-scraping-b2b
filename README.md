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
