@echo off
REM ====================================================================
REM  ESTADO_MOTOR.cmd  -  esta bien la pagina? Doble clic y listo.
REM
REM  Muestra en una pantalla: quien esta atendiendo la pagina por
REM  internet, con que clave de IA, si el tunel publica, si el arranque
REM  automatico esta puesto y que falta. SOLO MIRA: no cierra ni arranca
REM  nada.
REM
REM  Nacio el 04-08-2026: para saber si el sistema estaba bien habia que
REM  pegar cinco ordenes distintas en PowerShell y saber interpretarlas.
REM
REM  USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions
title MOTOR GLOSAS HUS - Estado del sistema

cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0estado_motor.ps1" -Repo "%CD%"

echo.
pause
