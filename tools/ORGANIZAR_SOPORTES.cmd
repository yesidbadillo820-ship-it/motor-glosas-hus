@echo off
REM ====================================================================
REM  ORGANIZAR_SOPORTES.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Mete cada soporte suelto de la carpeta del gestor DENTRO de la
REM  carpeta de su factura, y crea la carpeta si no existe.
REM
REM  Primero SIMULA (no toca nada) y muestra el listado. Solo si el
REM  auditor lo aprueba, mueve de verdad.
REM
REM  Se instala solo Python si falta. USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title ORGANIZAR SOPORTES - cada PDF en la carpeta de su factura

echo.
echo ============================================================
echo   ORGANIZAR SOPORTES - cada PDF en la carpeta de su factura
echo ============================================================
echo.

REM --- 1) Buscar Python (validando por ejecucion) ---------------------
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

REM --- 2) Localizar el motor Python -----------------------------------
set "MOTOR=%~dp0organizar_soportes_por_factura.py"
if exist "%MOTOR%" goto pedir
set "MOTOR=%~dp0tools\organizar_soportes_por_factura.py"
if exist "%MOTOR%" goto pedir
echo [ERROR] No encuentro organizar_soportes_por_factura.py junto a este .cmd
echo         ni en la subcarpeta tools\.
echo.
pause
exit /b 3

:pedir
REM --- 3) Carpeta del gestor ------------------------------------------
echo   Arrastre aca la carpeta del gestor (o pegue la ruta) y pulse Enter.
echo   Ejemplo: Z:\SERVIDOR GLOSAS\...\SOPORTES\TECNICOS\CAROLINA
echo.
set /p "CARPETA=  Carpeta: "
set "CARPETA=%CARPETA:"=%"
:quitarbs
if "%CARPETA:~-1%"=="\" ( set "CARPETA=%CARPETA:~0,-1%" & goto quitarbs )
if not defined CARPETA (
  echo [ERROR] No escribio ninguna carpeta.
  echo.
  pause
  exit /b 2
)
if not exist "%CARPETA%\" (
  echo [ERROR] Esa carpeta no existe o no hay acceso: %CARPETA%
  echo.
  pause
  exit /b 2
)

REM --- 4) Simulacion: mostrar que haria, sin tocar nada ----------------
echo.
echo ------------------------------------------------------------
echo   PASO 1 de 2 - SIMULACION (no se mueve nada todavia)
echo ------------------------------------------------------------
%PYEXE% "%MOTOR%" --carpeta "%CARPETA%"
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

REM --- 5) Confirmar antes de mover ------------------------------------
echo.
echo ------------------------------------------------------------
echo   PASO 2 de 2 - MOVER DE VERDAD
echo ------------------------------------------------------------
echo   Mover archivos NO se deshace. Revise el listado de arriba.
echo.
set "SEGURO="
set /p "SEGURO=  Escriba SI y pulse Enter para mover (cualquier otra cosa cancela): "
if /i not "%SEGURO%"=="SI" (
  echo.
  echo   Cancelado. No se movio nada.
  echo.
  pause
  exit /b 0
)

set "REPORTE=%CARPETA%\SOPORTES_ORGANIZADOS.csv"
%PYEXE% "%MOTOR%" --carpeta "%CARPETA%" --aplicar --reporte-csv "%REPORTE%"
echo.
echo   Listado de lo que se movio: %REPORTE%
echo.
pause
exit /b 0

:instalarpython
echo [ERROR] No encuentro Python en este equipo.
echo         Instalelo desde https://www.python.org/downloads/ marcando
echo         la casilla "Add Python to PATH" y vuelva a intentar.
echo.
pause
exit /b 4
