# Instrucciones para Claude Code en este repositorio

**Al iniciar cualquier sesión, lee primero `BITACORA.md`.** Es la memoria común
de todos los chats: ahí está lo que ya se hizo, lo que quedó pendiente y lo que
sigue.

**Al terminar la sesión, actualiza `BITACORA.md`** con:
- lo que se hizo hoy (en la sección de resumen por fecha, con la fecha del día),
- lo que quedó pendiente (sección "PENDIENTE"),
- lo próximo a trabajar (sección "PARA MAÑANA").

La bitácora se escribe en español claro, sin tecnicismos, pensando en un auditor
(no programador). Haz commit y push de la bitácora actualizada antes de cerrar.

## Contexto rápido del proyecto

Motor de Glosas HUS: sistema web + bots que apoyan a Cuentas Médicas / Cartera
del Hospital Universitario de Santander (ESE HUS) para responder glosas y
objeciones de las EPS. Contextos detallados por entidad en `docs/`
(`CONTEXTO_COOSALUD.md`, `CONTEXTO_DISPENSARIO_GLOSAS.md`,
`CONTEXTO_DISPENSARIO_NOTAS.md`) y guías de cada bot en `tools/README_*.md`.
