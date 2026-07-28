# Instrucciones del proyecto — Motor de Glosas HUS

## ⭐ PROTOCOLO DE BITÁCORA (leer y cumplir SIEMPRE)

Este repositorio usa **`BITACORA.md`** (en la raíz) como memoria común de
todas las sesiones y todos los chats de Claude Code.

- **Al INICIAR cualquier sesión:** lee primero **`BITACORA.md`**. Ahí está el
  resumen de todo lo trabajado, lo que quedó pendiente y lo que sigue.
- **Al TERMINAR la sesión:** actualiza **`BITACORA.md`** con:
  - lo que **se hizo hoy** (una entrada nueva, arriba, con la **fecha**),
  - lo que **quedó pendiente**,
  - lo que **sigue mañana**.
  Mantén el formato existente del archivo (sección de hechos por fecha,
  sección **PENDIENTE** y sección **PARA MAÑANA**). Después de actualizarla,
  haz commit y push de `BITACORA.md`.
- Escribe la bitácora en **español claro, sin tecnicismos**, pensando en el
  área de Cartera / Auditoría de Cuentas Médicas del HUS (no en programadores).

## Reglas del repo

- Escribir para el auditor: español claro, sin tecnicismos innecesarios.
- Nunca commitear usuarios ni contraseñas (siempre variables de entorno o
  archivos locales no versionados — ver "Secretos" abajo).
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

## Contexto rápido del proyecto

- **Motor de Glosas** (`app/`): aplicación web que genera con IA las respuestas
  técnico-jurídicas a las glosas de las EPS, según la norma colombiana. Incluye
  el módulo de **Pre-auditoría SINAC** (página `/preauditoria`).
- **Bots de carga** (`tools/`): suben las respuestas a cada portal — COOSALUD,
  SIMED (Dispensario Médico), Dinámica Gerencial (DGH), Mutual Ser, FOMAG, etc.
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
- **Secretos:** nunca subir contraseñas ni claves. Las claves de los portales
  de la Suite Cartera HUS van en `config/entidades.credenciales.json` (local,
  no versionado).
