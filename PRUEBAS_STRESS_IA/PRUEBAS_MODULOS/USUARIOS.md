# Usuarios

Pestaña del menú: `usuarios` · Rutas reales: `GET /usuarios/ · PATCH /{id}/rol · /activar`

**BOTÓN:** Usuarios
**OBJETIVO:** Que el rol se respete de verdad
**DATOS NECESARIOS:** Un usuario AUDITOR
**ARCHIVOS NECESARIOS:** Ninguno
**ACCIÓN EXACTA:** Entrar con un AUDITOR e intentar importar un paquete ADRES
**RESULTADO ESPERADO:** Debe salir «No tiene permiso para esto» con el rol y la ruta, NO «revise la conexión»
**ERROR QUE DEBEMOS BUSCAR:** Que el aviso culpe a la conexión · que un AUDITOR logre importar
