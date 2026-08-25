@echo off
REM ====================================================================
REM  UNIR_SOPORTES_ADRES.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Une los soportes de cada factura en UN SOLO PDF, en el orden que
REM  pide el area:
REM    1 RESPUESTA A GLOSA   2 EPICRISIS   3 HISTORIA CLINICA
REM    (urgencias, terapias, curaciones, evoluciones, procedimientos)
REM    4 AYUDAS DIAGNOSTICAS 5 MEDICAMENTOS 6 NOTAS DE ENFERMERIA
REM    7 INSUMOS             8 OTROS
REM  El DETALLADO queda en Excel, aparte: no entra al PDF.
REM
REM  Primero SIMULA (no toca nada) y muestra el orden. Solo si el
REM  auditor lo aprueba, une de verdad.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title UNIR SOPORTES ADRES - un solo PDF por factura, en orden

echo.
echo ============================================================
echo   UNIR SOPORTES ADRES - un solo PDF por factura, en orden
echo ============================================================
echo.

REM --- 1) Buscar Python (validando por ejecucion) ---------------------
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

REM --- 2) Localizar el motor Python -----------------------------------
set "MOTOR=%~dp0unir_soportes_adres.py"
if exist "%MOTOR%" goto dependencias
set "MOTOR=%~dp0tools\unir_soportes_adres.py"
if exist "%MOTOR%" goto dependencias
echo [ERROR] No encuentro unir_soportes_adres.py junto a este .cmd
echo         ni en la subcarpeta tools\.
echo.
pause
exit /b 3

:dependencias
%PYEXE% -c "import pypdf, openpyxl" >nul 2>&1
if errorlevel 1 (
  echo   Instalando pypdf y openpyxl (solo la primera vez)...
  %PYEXE% -m pip install --quiet pypdf openpyxl
)

REM --- 3) Carpeta del gestor ------------------------------------------
echo   Arrastre aca la carpeta del gestor (o pegue la ruta) y pulse Enter.
echo   Ejemplo: Z:\SERVIDOR GLOSAS\...\SOPORTES\TECNICOS\CAROLINA
echo.
set /p "CARPETA=  Carpeta: "
set "CARPETA=%CARPETA:"=%"
:quitarbs
if "%CARPETA:~-1%"=="\" ( set "CARPETA=%CARPETA:~0,-1%" & goto quitarbs )
if not exist "%CARPETA%\" (
  echo [ERROR] Esa carpeta no existe o no hay acceso: %CARPETA%
  echo.
  pause
  exit /b 2
)

echo.
echo   (Opcional) Excel con las facturas a trabajar. Enter para todas.
set /p "LISTA=  Lista: "
set "LISTA=%LISTA:"=%"
set "ARGLISTA="
if defined LISTA if exist "%LISTA%" set "ARGLISTA=--facturas "%LISTA%""

set "REPORTE=%CARPETA%\SOPORTES_UNIDOS.csv"

REM --- 4) Simulacion: mostrar el orden, sin escribir nada --------------
echo.
echo ------------------------------------------------------------
echo   PASO 1 de 2 - SIMULACION (no se une nada todavia)
echo ------------------------------------------------------------
%PYEXE% "%MOTOR%" --carpeta "%CARPETA%" %ARGLISTA% --reporte-csv "%REPORTE%"
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

echo.
echo   El listado completo quedo en: %REPORTE%
echo   Revise sobre todo los archivos que dice NO RECONOCIDOS.
echo.

REM --- 5) Confirmar antes de unir -------------------------------------
echo ------------------------------------------------------------
echo   PASO 2 de 2 - UNIR DE VERDAD
echo ------------------------------------------------------------
set "SEGURO="
set /p "SEGURO=  Escriba SI y pulse Enter para unir (cualquier otra cosa cancela): "
if /i not "%SEGURO%"=="SI" (
  echo.
  echo   Cancelado. No se unio nada.
  echo.
  pause
  exit /b 0
)

%PYEXE% "%MOTOR%" --carpeta "%CARPETA%" %ARGLISTA% --aplicar --reporte-csv "%REPORTE%"
echo.
echo   Cada factura quedo con su PDF unido: ^<FACTURA^>_SOPORTES.pdf
echo   Listado de que archivo quedo en que grupo: %REPORTE%
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
