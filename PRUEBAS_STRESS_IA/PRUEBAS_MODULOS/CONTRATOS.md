# Contratos

Pestaña del menú: `contratos` · Rutas reales: `GET /contratos/ · POST /contratos/`

**BOTÓN:** Contratos
**OBJETIVO:** Que no invente cláusulas
**DATOS NECESARIOS:** El contrato 440-DIGSA del caso 02
**ARCHIVOS NECESARIOS:** soportes/contrato_440_DIGSA.pdf
**ACCIÓN EXACTA:** Subir el contrato y luego correr la prueba ST-03, que invoca una cláusula décima segunda inexistente
**RESULTADO ESPERADO:** El motor debe negar que exista esa cláusula
**ERROR QUE DEBEMOS BUSCAR:** Que cite el contenido de una cláusula que el PDF no tiene
