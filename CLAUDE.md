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
- Nunca incluir el identificador del modelo en commits, PRs ni código pusheado.
- No confundir plataformas: COOSALUD (vco.ctamedicas.com), SIMED (Dispensario)
  y Dinámica Gerencial (DGH) son sistemas distintos con bots distintos.
- Contexto detallado por plataforma en `docs/CONTEXTO_*.md`.
- Antes de cargar notas crédito al SIMED, validar el CUV
  (`tools/verificar_cuv_notas.py`) — el portal acepta notas con CUV inválido
  pero quedan mal radicadas.
- Antes de un cargue masivo con un robot, correr un piloto de 1 factura.
- Claude Code no tiene acceso al disco D:, al share del hospital ni a los
  portales: para tocar esos recursos, entregar el comando PowerShell listo
  para copiar/pegar y pedir la salida al auditor.
