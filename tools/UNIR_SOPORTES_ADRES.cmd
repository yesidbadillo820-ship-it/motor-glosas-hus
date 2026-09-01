@echo off
REM ====================================================================
REM  UNIR_SOPORTES_ADRES.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Deja cada factura con sus DOS folios, con el nombre con que se suben
REM  al ADRES:
REM
REM    <NIT>_<FACTURA>_EPICRIS.pdf   (folio clinico)
REM       1 RESPUESTA A GLOSA  2 EPICRISIS  3 HISTORIA CLINICA
REM       4 AYUDAS DIAGNOSTICAS 5 MEDICAMENTOS 6 NOTAS DE ENFERMERIA
REM       7 INSUMOS            8 OTROS
REM
REM    <NIT>_<FACTURA>_FACTURA.pdf   (folio de la factura)
REM       1 FACTURA  2 DETALLADO  3 REPRESENTACION GRAFICA DIAN
REM       4 NOTAS CREDITO  (PENDIENTE: todavia no las han sacado)
REM
REM  Primero SIMULA (no toca nada) y muestra como quedarian los dos
REM  folios. Solo si el auditor lo aprueba, los arma de verdad.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title FOLIOS ADRES - los dos PDF de cada factura

echo.
echo ============================================================
echo   FOLIOS ADRES - los dos PDF de cada factura
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

REM --- 4) Carpeta de las facturas con XML -----------------------------
echo.
echo   Carpeta donde estan los PDF de las facturas (la del XML).
echo   Ejemplo: Z:\...\4.PAQUETE 31068-RAD.JULIO 9\4.FACTURAS CON XML\XML
echo   Enter para saltarla (el folio de la factura quedaria incompleto).
set /p "FACTURAS=  Facturas: "
set "FACTURAS=%FACTURAS:"=%"
set "ARGFAC="
if defined FACTURAS if exist "%FACTURAS%\" set "ARGFAC=--carpeta-facturas "%FACTURAS%""

echo.
echo   (Opcional) Excel con las facturas a trabajar. Enter para todas.
set /p "LISTA=  Lista: "
set "LISTA=%LISTA:"=%"
set "ARGLISTA="
if defined LISTA if exist "%LISTA%" set "ARGLISTA=--facturas "%LISTA%""

set "REPORTE=%CARPETA%\FOLIOS_ADRES.csv"

REM --- 5) Simulacion: mostrar los folios, sin escribir nada ------------
echo.
echo ------------------------------------------------------------
echo   PASO 1 de 2 - SIMULACION (no se arma nada todavia)
echo ------------------------------------------------------------
%PYEXE% "%MOTOR%" --folio --carpeta "%CARPETA%" %ARGFAC% %ARGLISTA% --convertir-detallado --reporte-csv "%REPORTE%"
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

echo.
echo   El listado completo quedo en: %REPORTE%
echo   Revise sobre todo los archivos que dice NO RECONOCIDOS.
echo.

REM --- 6) Confirmar antes de armar ------------------------------------
echo ------------------------------------------------------------
echo   PASO 2 de 2 - ARMAR LOS FOLIOS DE VERDAD
echo ------------------------------------------------------------
set "SEGURO="
set /p "SEGURO=  Escriba SI y pulse Enter para armarlos (cualquier otra cosa cancela): "
if /i not "%SEGURO%"=="SI" (
  echo.
  echo   Cancelado. No se armo nada.
  echo.
  pause
  exit /b 0
)

%PYEXE% "%MOTOR%" --folio --carpeta "%CARPETA%" %ARGFAC% %ARGLISTA% --convertir-detallado --aplicar --reporte-csv "%REPORTE%"
echo.
echo   Cada factura quedo con sus dos folios:
echo     ^<NIT^>_^<FACTURA^>_EPICRIS.pdf   y   ^<NIT^>_^<FACTURA^>_FACTURA.pdf
echo   Listado de que archivo quedo en que renglon: %REPORTE%
echo.
echo   Las NOTAS CREDITO quedan pendientes a proposito. Cuando salgan,
echo   dejelas en la carpeta de la factura y vuelva a correr este bot:
echo   entran solas de cuartas, sin rehacer nada.
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
