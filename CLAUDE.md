# Instrucciones para Claude Code en este repositorio

## Bitácora (obligatorio)

- **Al iniciar cualquier sesión, lee primero `BITACORA.md`** — es la memoria común
  de todos los chats: qué se ha hecho, qué está pendiente y qué sigue.
- **Al terminar la sesión, actualiza `BITACORA.md`** con:
  - lo que se hizo hoy (con la fecha),
  - lo que quedó pendiente,
  - lo próximo a trabajar mañana.
- Escribe la bitácora en español, claro y sin tecnicismos, pensando en un
  auditor (no programador).

## Contexto del proyecto

- Los procesos y reglas de cada frente están en `docs/`:
  - `docs/CONTEXTO_COOSALUD.md` — glosas COOSALUD (DGH + portal VCO).
  - `docs/CONTEXTO_DISPENSARIO_GLOSAS.md` y `docs/CONTEXTO_DISPENSARIO_NOTAS.md`.
- Los bots de escritorio viven en `tools/`.
- Nunca escribir usuarios ni contraseñas en el código: van en variables de
  entorno (ver los contextos).
- No confundir COOSALUD con SIMED: son EPS y flujos distintos.
