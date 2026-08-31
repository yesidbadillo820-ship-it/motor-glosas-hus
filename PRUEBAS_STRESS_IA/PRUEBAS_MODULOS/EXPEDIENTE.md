# Expediente

Pestaña del menú: `expediente` · Rutas reales: `GET /soportes/*`

**BOTÓN:** Expediente
**OBJETIVO:** Que no diga «sin soportes» mientras indexa
**DATOS NECESARIOS:** Una factura con soportes
**ARCHIVOS NECESARIOS:** Los PDF del caso 02
**ACCIÓN EXACTA:** Abrir el expediente de una factura mientras el índice se reconstruye
**RESULTADO ESPERADO:** Debe decir que está indexando, NO «no hay soportes»
**ERROR QUE DEBEMOS BUSCAR:** «Sin soportes» cuando el índice está a medio armar — es el defecto del 27-08
