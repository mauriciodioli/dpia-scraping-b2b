# Estado de la prueba funcional

El almacenamiento local de contador e historial fue retirado por solicitud del
usuario. Los módulos `query_store.py` y `scraping_quota.py`, sus tablas locales y
su configuración ya no forman parte de la aplicación.

No se implementó otra persistencia ni se modificó MySQL. El workflow YAML fue
editado por el usuario y no se modificó durante esta retirada.

El contador, el historial y la ejecución facturable permanecen no disponibles hasta
definir una persistencia autorizada. Las consultas de texto a publicaciones
existentes permanecen disponibles. No se muestran saldos inventados ni se habilitan
pagos. No se ejecutó ninguna prueba facturable ni despliegue.
