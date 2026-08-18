@echo off
REM ====================================================================
REM  ORGANIZAR_TRABAJOS_BOTS.cmd  -  Bot de doble clic del Motor Glosas HUS.
REM  Arma (o actualiza) la carpeta "D:\TRABAJOS BOTS": una carpeta por
REM  frente de trabajo (COOSALUD, SIMED, DGH, SIIFA, ADRES, Suite
REM  Cartera, etc.) con accesos directos a los bots de doble clic y un
REM  LEEME.txt en español sencillo por carpeta (que bot usar, cuando, y
REM  el comando listo para copiar si el bot no tiene doble clic).
REM
REM  No copia ni mueve nada del repositorio, solo crea accesos directos
REM  y archivos de guia: se puede correr las veces que haga falta.
REM  USO: doble clic. Se puede correr de nuevo cuando se agregue un bot
REM  nuevo, para que "D:\TRABAJOS BOTS" quede al dia.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title ORGANIZAR TRABAJOS BOTS - Motor Glosas HUS

echo.
echo ============================================================
echo   ORGANIZAR TRABAJOS BOTS - Motor Glosas HUS
echo ============================================================
echo.
echo   Esto va a crear/actualizar la carpeta:
echo     D:\TRABAJOS BOTS
echo   con una carpeta por frente de trabajo (COOSALUD, SIMED, DGH,
echo   SIIFA, ADRES, Suite Cartera, etc.), sus accesos directos y una
echo   guia LEEME.txt en cada una.
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0organizar_trabajos_bots.ps1"
if errorlevel 1 (
  echo.
  echo   [!] Algo fallo. Revisa el mensaje de arriba.
  echo.
)

echo.
pause
