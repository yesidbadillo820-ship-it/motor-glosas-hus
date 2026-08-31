# Mando ejecutivo

Pestaña del menú: `mando` · Rutas reales: `GET /dashboard-ejecutivo/vivo · /operacion`

**BOTÓN:** Mando ejecutivo
**OBJETIVO:** Que solo lo vea coordinador o admin
**DATOS NECESARIOS:** Un usuario AUDITOR y uno COORDINADOR
**ARCHIVOS NECESARIOS:** Ninguno
**ACCIÓN EXACTA:** Entrar con cada rol y mirar el menú
**RESULTADO ESPERADO:** El AUDITOR no ve la opción; el COORDINADOR sí
**ERROR QUE DEBEMOS BUSCAR:** Que el AUDITOR la vea o que la ruta responda a quien no debe
