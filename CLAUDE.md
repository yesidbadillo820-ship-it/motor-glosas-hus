# Instrucciones del proyecto — Motor de Glosas HUS

## ⭐ PROTOCOLO DE BITÁCORA (leer y cumplir SIEMPRE)

Este repositorio usa **`BITACORA.md`** como memoria común de todas las sesiones.

- **Al INICIAR cualquier sesión:** lee primero **`BITACORA.md`**. Ahí está el
  resumen de todo lo trabajado, lo que quedó pendiente y lo que sigue.
- **Al TERMINAR la sesión:** actualiza **`BITACORA.md`** con:
  - lo que **se hizo hoy** (una entrada nueva, arriba, con la **fecha**),
  - lo que **quedó pendiente**,
  - lo que **sigue mañana**.
- Escribe la bitácora en **español claro, sin tecnicismos**, pensando en el
  área de Cartera / Auditoría de Cuentas Médicas (no en programadores).

## Contexto rápido del proyecto

- **Motor de Glosas** (`app/`): aplicación web que genera con IA las respuestas
  técnico-jurídicas a las glosas de las EPS, según la norma colombiana.
- **Suite Cartera HUS** (`tools/suite_cartera_hus/`): programa de escritorio del
  analista (organizar portales → consolidar glosas → cruzar DGH → OBJECIONES),
  con una **caja de Herramientas PDF** (botón 🧰). Tiene versión de ventana
  (`suite_cartera_hus.py`) y de consola (`suite_cli.py`).
- Historia detallada por fechas: ver `CHANGELOG.md` y, en lenguaje llano,
  `BITACORA.md`.

## Notas técnicas útiles

- **Pruebas:** `pytest` (config en `pytest.ini`, tests en `tests/`). CI corre
  `ruff check . --select F,W6` + `ruff format --check .` + `pytest`. Antes de
  hacer commit, deja el código formateado con `ruff format` y sin errores F/W6.
- **Rama de trabajo actual:** `claude/bot-multifunctional-improvements-zhj4nw`
  (PR #160, en borrador). La rama principal del repo es `motor-glosas`.
- **Secretos:** nunca subir contraseñas ni claves. Las claves de los portales
  van en `config/entidades.credenciales.json` (local, no versionado).
