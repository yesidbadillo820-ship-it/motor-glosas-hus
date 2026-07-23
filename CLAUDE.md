# Instrucciones para Claude Code en este repositorio

**Al iniciar cualquier sesión, lee primero `BITACORA.md`** (en la raíz del
repo). Es la memoria común de todos los chats: qué se ha hecho, qué está
pendiente y qué sigue.

**Al terminar la sesión, actualiza `BITACORA.md`** con:
- lo que se hizo hoy,
- lo que quedó pendiente,
- lo que sigue mañana,
- siempre con la **fecha** del día.

Escribe la bitácora en español claro, pensando en un auditor de cartera
(no en un programador). Mantén el formato existente: sección de hechos por
fecha, sección **PENDIENTE** y sección **PARA MAÑANA**.
Después de actualizarla, haz commit y push de `BITACORA.md`.

## Reglas del repo

- Escribir para el auditor: español claro, sin tecnicismos innecesarios.
- Nunca commitear usuarios ni contraseñas (siempre variables de entorno).
- Nunca incluir el identificador del modelo en commits, PRs ni código pusheado.
- No confundir plataformas: COOSALUD (vco.ctamedicas.com), SIMED (Dispensario)
  y Dinámica Gerencial (DGH) son sistemas distintos con bots distintos.
- Antes de cargar notas crédito al SIMED, validar el CUV
  (`tools/verificar_cuv_notas.py`) — el portal acepta notas con CUV inválido
  pero quedan mal radicadas.
- Antes de un cargue masivo con un robot, correr un piloto de 1 factura.
- Claude Code no tiene acceso al disco D:, al share del hospital ni a los
  portales: para tocar esos recursos, entregar el comando PowerShell listo
  para copiar/pegar y pedir la salida al auditor.

Contexto adicional por flujo de trabajo (léelos cuando el tema aplique):
- `docs/CONTEXTO_DISPENSARIO_GLOSAS.md` — respuesta de glosas del Dispensario en SIMED.
- `docs/CONTEXTO_DISPENSARIO_NOTAS.md` — cargue de notas crédito en SIMED.
- `docs/CONTEXTO_COOSALUD.md` — respuesta de glosas COOSALUD.
