# Vencimientos

Pestaña del menú: `vencimientos` · Rutas reales: `GET /alertas/vencimientos · /proximas`

**BOTÓN:** Vencimientos
**OBJETIVO:** Que el cero no mienta
**DATOS NECESARIOS:** Cortar la red o parar el backend
**ARCHIVOS NECESARIOS:** Ninguno
**ACCIÓN EXACTA:** Con el backend caído, recargar el inicio y mirar la tarjeta «Próximas a vencer»
**RESULTADO ESPERADO:** Debe mostrar «—» y «no se pudo consultar», NUNCA 0 en verde
**ERROR QUE DEBEMOS BUSCAR:** Un 0 tranquilizador cuando en realidad no se pudo preguntar
