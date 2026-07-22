# CLAUDE.md — instrucciones para todos los chats de este repo

## Memoria común (LO PRIMERO Y LO ÚLTIMO)

1. **Al iniciar cualquier sesión, lee primero `BITACORA.md`.** Ahí está el
   registro de todo lo que se ha trabajado, lo que quedó pendiente y lo que
   sigue. Es la memoria común entre todos los chats.

2. **Al terminar, actualiza `BITACORA.md`** con:
   - lo que se hizo hoy (con la **fecha**),
   - lo que quedó **pendiente**,
   - lo que sigue **para mañana**.
   Luego haz **commit y push** de los cambios.

   > Si el usuario cierra el chat sin pedirlo, igual conviene ofrecer actualizar
   > la bitácora antes de terminar.

## Sobre este proyecto

Bots de **doble clic** (`tools/*.cmd`) para el área de **auditoría de cuentas
del HUS**: prevenir y responder **glosas y devoluciones** de las EPS (sobre todo
Nueva EPS). El usuario es **auditor, no programador** — explícale en español
claro, sin tecnicismos.

- El menú central es **`tools/MOTOR_HUS.cmd`**.
- Cada bot tiene su motor en `tools/<nombre>.py` **embebido** dentro del `.cmd`
  (después del marcador `#PYSTART#`). Si cambias un `.py`, hay que **regenerar
  el `.cmd`** para que el motor embebido quede idéntico (lo verifican las
  pruebas). Los ensambladores están en la carpeta de trabajo temporal (scratchpad).
- Guías para el usuario: `tools/README_*.md` y `tools/README_KIT_AUDITORIA.md`.

## Reglas de calidad (mantener en verde)

- Antes de dar por terminado un cambio de código:
  `python3 -m pytest tests/test_tools/ -q` y
  `python3 -m ruff check . --select F,W6` + `python3 -m ruff format --check`.
- Los bots **nunca** tocan los archivos originales del usuario (escriben copias).
- Datos de facturación como **texto** (ceros a la izquierda, NIT largos, fechas).
- Un archivo dañado no detiene el resto: se reporta y se sigue.

## Git

- Rama de trabajo actual: **`claude/powershell-pdf-cmd-bot-3iaihn`** (PR #156).
- Commit y push cuando el usuario lo pida o al cerrar una tarea; mensajes claros
  en español.
