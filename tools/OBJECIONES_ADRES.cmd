@echo off
REM ====================================================================
REM  OBJECIONES_ADRES.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Pasa las glosas del ADRES (el Excel "ADRES DANIEL") al formato
REM  OBJECIONES de 16 columnas que recibe Dinamica Gerencial (DGH).
REM
REM  Homologa el codigo del servicio contra el DGReport y el Homologador
REM  Gold Standard CUPS/SOAT. Lo que no logra homologar NO lo inventa:
REM  lo deja vacio y lo lista en el archivo REVISAR.
REM
REM  Se instala solo openpyxl si falta. USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title OBJECIONES ADRES - pasar las glosas del ADRES al formato de DGH

echo.
echo ============================================================
echo   OBJECIONES ADRES - del Excel del ADRES al formato de DGH
echo ============================================================
echo.

REM --- 1) Buscar Python (validando por ejecucion) ---------------------
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

REM --- 2) Localizar el motor Python -----------------------------------
set "MOTOR=%~dp0organizar_objeciones_adres.py"
if exist "%MOTOR%" goto dependencias
set "MOTOR=%~dp0tools\organizar_objeciones_adres.py"
if exist "%MOTOR%" goto dependencias
echo [ERROR] No encuentro organizar_objeciones_adres.py junto a este .cmd
echo         ni en la subcarpeta tools\.
echo.
pause
exit /b 3

:dependencias
%PYEXE% -c "import openpyxl" >nul 2>&1
if errorlevel 1 (
  echo   Instalando openpyxl (solo la primera vez)...
  %PYEXE% -m pip install --quiet openpyxl
)

REM --- 3) Pedir los tres archivos -------------------------------------
echo   Arrastre aca cada archivo (o pegue la ruta) y pulse Enter.
echo.
set /p "ADRES=  1) Excel de glosas del ADRES  : "
set "ADRES=%ADRES:"=%"
if not exist "%ADRES%" (
  echo [ERROR] No existe ese archivo: %ADRES%
  echo.
  pause
  exit /b 2
)

set /p "DGH=  2) DGReport de DGH           : "
set "DGH=%DGH:"=%"
if not exist "%DGH%" (
  echo [ERROR] No existe ese archivo: %DGH%
  echo         Sin el DGReport no se puede poner el codigo de servicio.
  echo.
  pause
  exit /b 2
)

set /p "HOM=  3) Homologador CUPS/SOAT      : "
set "HOM=%HOM:"=%"
if not exist "%HOM%" (
  echo [ERROR] No existe ese archivo: %HOM%
  echo.
  pause
  exit /b 2
)

set /p "PAQUETE=  4) Numero de paquete (Enter = todos): "
set "PAQUETE=%PAQUETE:"=%"

REM --- 4) Carpeta de salida, al lado del Excel del ADRES ---------------
for %%A in ("%ADRES%") do set "DESTINO=%%~dpAOBJECIONES_ADRES"

echo.
echo ------------------------------------------------------------
echo   Generando en: %DESTINO%
echo ------------------------------------------------------------
echo.
if defined PAQUETE (
  %PYEXE% "%MOTOR%" --adres "%ADRES%" --dgh "%DGH%" --homologador "%HOM%" --salida "%DESTINO%" --paquete "%PAQUETE%"
) else (
  %PYEXE% "%MOTOR%" --adres "%ADRES%" --dgh "%DGH%" --homologador "%HOM%" --salida "%DESTINO%"
)
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

echo.
echo ------------------------------------------------------------
echo   ANTES DE CARGAR EN DGH
echo ------------------------------------------------------------
echo   1. Abra REVISAR_OBJECIONES_ADRES.xlsx, hoja CODIGOS: el ADRES
echo      usa codigos numericos (3106, 3209...) y DGH los de seis del
echo      Manual Unico (SO3401, CL0101...). Complete la equivalencia.
echo   2. Mire la hoja REVISAR: ahi estan los renglones sin codigo de
echo      servicio, con el candidato mas parecido.
echo   3. Haga el piloto de UNA factura antes del cargue masivo.
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
