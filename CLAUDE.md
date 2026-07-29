# Instrucciones para Claude Code en este repositorio

## Memoria común: BITACORA.md

**Al iniciar cualquier sesión, lee primero `BITACORA.md`** (en la raíz del
repositorio). Es la memoria común de todos los chats: qué se ha hecho, qué
está pendiente y qué sigue.

**Al terminar la sesión, actualiza `BITACORA.md`** con:
- lo que se hizo hoy (agregado en "LO YA HECHO" con la fecha),
- lo que quedó pendiente (sección "PENDIENTE"),
- lo próximo a trabajar (sección "PARA MAÑANA"),
e incluye la actualización en el commit final (y push).

Escribe la bitácora **en español, claro y sin tecnicismos**: el dueño del
repositorio es un auditor de salud, no un programador. Mantén el formato
existente (hechos por fecha, PENDIENTE, PARA MAÑANA).

## Contexto del proyecto

- Dueño: auditoría de facturación de la E.S.E. Hospital Universitario de
  Santander (HUS). Los mensajes del usuario llegan en español; responde
  siempre en español.
- Este repo tiene dos frentes:
  1. **Motor Glosas** (`app/`): plataforma web que responde glosas con IA
     (incluye pre-auditoría y los flujos de Dispensario/SIMED y COOSALUD).
  2. **Módulo ADRES/FURIPS** (`tools/adres/`, `validador-adres/`,
     `tools/*.cmd`): validación de reclamaciones FURIPS (Circular 022/2023),
     informes Excel/Word y bots de doble clic para Windows.
- Los `.cmd` de `tools/` son bots de doble clic para auditores en Windows:
  deben conservar finales de línea CRLF (ya hay regla en `.gitattributes`)
  y autoinstalar sus dependencias.
- Las entregas al usuario suelen ser: archivo(s) listos para copiar al
  servidor de cartera + commit/push + pull request en borrador.

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
- `docs/ENTREGA_MODULO_ADRES_FURIPS.md` — entrega técnica del módulo ADRES/FURIPS.
