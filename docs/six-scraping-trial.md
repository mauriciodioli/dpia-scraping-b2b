# Prueba funcional: contador MySQL

El usuario creó manualmente `pwa_scraping_cupos` y `pwa_scraping_operaciones`.
Flask utiliza esas tablas para cupos, reservas, idempotencia y resultados.
No hay SQLite de aplicación, creación automática de tablas ni cambios al YAML.

La recarga de seis ejecuciones exige DEBUG y ENABLE_TEST_SCRAPING_CREDITS=true.
Los proveedores permanecen controlados por LIVE_PROVIDER_CALLS_ENABLED.
No se habilitan pagos ni se contabilizan tokens o costos de Apify.

Las pruebas nuevas simulan conexiones SQL y proveedores: verifican el bloqueo
FOR UPDATE antes del conteo, UUID/payload/usuario, agotamiento, transiciones,
reutilización de resultados y restricciones de recarga. La inspección real de
MySQL se limita a metadatos. La concurrencia contra un MySQL real no se ha
probado todavía; las simulaciones no sustituyen esa validación.

No se ejecutó scraping real, OpenAI, commit, push ni despliegue.
