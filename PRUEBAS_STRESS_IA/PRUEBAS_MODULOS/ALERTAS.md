# Alertas

Pestaña del menú: `alertas` · Rutas reales: `GET /alertas/proximas · /config · POST /alertas/enviar`

**BOTÓN:** Alertas
**OBJETIVO:** Que el badge rojo corresponda a plazos reales
**DATOS NECESARIOS:** Glosas próximas a vencer
**ARCHIVOS NECESARIOS:** Ninguno
**ACCIÓN EXACTA:** Comparar el badge del menú con la lista de alertas
**RESULTADO ESPERADO:** El mismo número
**ERROR QUE DEBEMOS BUSCAR:** Alertas de glosas ya cerradas · badge que no baja al resolver
