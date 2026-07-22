# Instrucciones para Claude Code en este repo

**Al iniciar cualquier sesión, lee primero `BITACORA.md`** (en la raíz del
repo). Es la memoria común de todos los chats: qué se ha hecho, qué está
pendiente y qué sigue.

**Al terminar la sesión, actualiza `BITACORA.md`** con:
- lo que se hizo hoy (con la fecha),
- lo que quedó pendiente,
- lo que sigue mañana.

Después de actualizarla, haz commit y push de `BITACORA.md`.

## Reglas del repo

- Rama de trabajo: `claude/excel-reconciliation-data-9Bnpj`.
- Escribir para el auditor: español claro, sin tecnicismos innecesarios.
- Nunca commitear usuarios ni contraseñas (siempre variables de entorno).
- No confundir plataformas: COOSALUD (vco.ctamedicas.com), SIMED (Dispensario)
  y Dinámica Gerencial (DGH) son sistemas distintos con bots distintos.
- Contexto detallado por plataforma en `docs/CONTEXTO_*.md`.
