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
repositorio es un auditor de salud, no un programador.

## Contexto del proyecto

- Dueño: auditoría de facturación de la E.S.E. Hospital Universitario de
  Santander (HUS). Los mensajes del usuario llegan en español; responde
  siempre en español.
- Este repo tiene dos frentes:
  1. **Motor Glosas** (`app/`): plataforma web que responde glosas con IA.
  2. **Módulo ADRES/FURIPS** (`tools/adres/`, `validador-adres/`,
     `tools/*.cmd`): validación de reclamaciones FURIPS (Circular 022/2023),
     informes Excel/Word y bots de doble clic para Windows.
- Los `.cmd` de `tools/` son bots de doble clic para auditores en Windows:
  deben conservar finales de línea CRLF (ya hay regla en `.gitattributes`)
  y autoinstalar sus dependencias.
- Las entregas al usuario suelen ser: archivo(s) listos para copiar al
  servidor de cartera + commit/push + pull request en borrador.
