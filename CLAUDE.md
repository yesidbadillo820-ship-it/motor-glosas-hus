# CLAUDE.md — Instrucciones para el asistente

## 🧭 Regla principal: la bitácora es la memoria común

**Al iniciar CUALQUIER sesión, lee primero `BITACORA.md`.** Ahí está el resumen de
todo lo hecho, lo que quedó pendiente y lo que sigue. Es el control central del
trabajo y la memoria compartida entre todos los chats.

**Al terminar la sesión, actualiza `BITACORA.md`** con:
- lo que se hizo hoy,
- lo que quedó pendiente,
- lo que sigue para mañana,

siempre **con la fecha**. Agrega una entrada nueva con la fecha del día en la
sección "Lo que se ha hecho", y refresca las secciones **PENDIENTE** y
**PARA MAÑANA**. Actualiza también la línea "Última actualización".

> Escribe la bitácora en español, claro y sin tecnicismos, pensando en un
> auditor (no en un programador).

---

## Sobre el proyecto

Repositorio del área de **Cuentas Médicas y Cartera** de la ESE Hospital
Universitario de Santander. Contiene:

- **Motor de Glosas** (`app/`): aplicación web que redacta respuestas a glosas de las EPS.
- **Suite de Radicación y Cartera** (`tools/`): herramientas que revisan las facturas
  antes de radicarlas, cruzan sus soportes, y controlan la cartera. Piezas clave:
  `radicar_facturacion.py` (motor), `explorador_radicacion.py` (buscador),
  `tablero_cartera.py` (control de plata), `diag_soportes.py` (diagnóstico).

## Regla de seguridad (no negociable)

Las herramientas de radicación son **solo lectura** sobre las carpetas del hospital:
no modifican, mueven ni borran archivos. Solo generan reportes nuevos. **No** usar
las opciones que copian o mueven archivos (`--armar` / `--mover`) salvo que la
persona usuaria lo pida explícitamente.

## Notas técnicas para el asistente

- Los reportes del radicador (CSV/XLSX) alimentan al explorador y al tablero: no
  cambiar los nombres de las columnas sin avisar.
- Antes de dar por terminado un cambio de código: correr las pruebas y el linter.
  - Pruebas de las herramientas: `python -m pytest tests/test_tools/ -q`
  - Linter: `ruff check --select F,W6` y `ruff format --check`
- El código y los comentarios van en español, siguiendo el estilo del archivo.
