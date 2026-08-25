@echo off
REM ====================================================================
REM  VERIFICAR_CATALOGOS_SOAT.cmd  -  quedo bien instalado el SOAT 2026?
REM
REM  Doble clic y en una pantalla dice si el servidor tiene las dos
REM  tablas que sostienen cualquier defensa de tarifa:
REM    1) el homologador CUPS -> SOAT (Gold Standard 2026)
REM    2) el Manual SOAT 2026 (Circular Externa 047 de 2025)
REM
REM  Termina diciendo VERIFICADO o FALLA. SOLO MIRA: no cambia nada.
REM
REM  USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions
title MOTOR GLOSAS HUS - Verificar catalogos SOAT 2026

cd /d "%~dp0.."

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

set DISABLE_SCHEDULERS=1
"%PY%" tools\verificar_catalogos_soat.py

echo.
pause
