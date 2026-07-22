# CLAUDE.md — Instrucciones para toda sesión de Claude Code en este repo

## Memoria común del proyecto (OBLIGATORIO)

**Al iniciar cualquier sesión, lee primero `BITACORA.md`** — ahí está todo lo
trabajado hasta hoy, lo pendiente y lo próximo. No empieces a trabajar sin
leerla.

**Al terminar la sesión, actualiza `BITACORA.md`** con:
- lo que se hizo hoy (con la fecha),
- lo que quedó pendiente,
- lo que sigue mañana.

Haz commit y push de la bitácora actualizada junto con el trabajo del día.

## Contexto rápido

- Proyecto: gestión de glosas y cartera de la ESE Hospital Universitario de
  Santander (HUS), operado por SINAC SC.
- La aplicación web (motor de glosas con IA) vive en `app/`; los bots de
  portales y herramientas de apoyo en `tools/` (cada uno con su `README_*.md`);
  los scripts de datos en `scripts/`; las pruebas en `tests/`.
- Escribe commits, documentación y mensajes al usuario en **español**, en
  lenguaje claro (el usuario es auditor, no programador).
- Antes de commitear código Python: `ruff check` + `ruff format` y corre los
  tests del área tocada (`python -m pytest tests/...`).
