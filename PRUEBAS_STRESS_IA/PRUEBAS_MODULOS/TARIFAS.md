# Tarifas

Pestaña del menú: `tarifas` · Rutas reales: `GET /tarifas-contratadas/ · /buscar · POST /import-csv · /import-excel`

**BOTÓN:** Tarifas
**OBJETIVO:** Que aplique el factor del contrato
**DATOS NECESARIOS:** El contrato 440-DIGSA (SOAT −20 %, factor 0.8)
**ARCHIVOS NECESARIOS:** tarifas_prueba.xlsx
**ACCIÓN EXACTA:** Cargar el Excel de tarifas y liquidar un servicio del contrato 440-DIGSA
**RESULTADO ESPERADO:** Debe aplicar factor 0.8, no SOAT pleno
**ERROR QUE DEBEMOS BUSCAR:** SOAT PLENO cuando el contrato dice −20 % — es el pendiente abierto del 440-DIGSA
