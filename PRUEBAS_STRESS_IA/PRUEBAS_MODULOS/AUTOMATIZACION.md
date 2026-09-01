# Automatización

Pestaña del menú: `automatizacion` · Rutas reales: `GET /automatizaciones/ · POST /{id}/previsualizar · /ejecutar`

**BOTÓN:** Automatización
**OBJETIVO:** Que previsualizar no ejecute
**DATOS NECESARIOS:** Una automatización configurada
**ARCHIVOS NECESARIOS:** Ninguno
**ACCIÓN EXACTA:** Pulsar «previsualizar» y verificar que NO se creó ni modificó nada
**RESULTADO ESPERADO:** Solo muestra qué haría
**ERROR QUE DEBEMOS BUSCAR:** Que la previsualización ya haya escrito en la base
