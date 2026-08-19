@echo off
REM ====================================================================
REM  VERIFICAR_TRABAJO_HOY.cmd  -  quedo bien lo del 19-08-2026?
REM
REM  Doble clic y en una pantalla dice si el servidor tiene las cuatro
REM  cosas que se entregaron hoy:
REM    1) Glosas ADRES muestra las CANTIDADES (reclamada / aprobada / glosada)
REM    2) Al ADRES no se le declara dos veces la misma plata
REM    3) "Aplicar sugerencias" ya no acepta glosas por $0
REM    4) El Auditor Forense abre los documentos correctos y vive
REM       dentro de "Analizar glosa"
REM
REM  Le pide el numero de una factura radicada (opcional) para probar el
REM  forense contra los soportes REALES del servidor.
REM
REM  Termina diciendo VERIFICADO o FALLA. SOLO MIRA: no cambia nada,
REM  no llama a la IA y no cuesta un peso.
REM
REM  USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions
title MOTOR GLOSAS HUS - Verificar el trabajo del 19-08

cd /d "%~dp0.."

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

set DISABLE_SCHEDULERS=1
"%PY%" tools\verificar_trabajo_hoy.py

echo.
pause
