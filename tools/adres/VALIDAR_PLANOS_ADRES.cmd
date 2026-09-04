@echo off
REM ====================================================================
REM  VALIDAR_PLANOS_ADRES.cmd  -  Bot de doble clic del Motor Glosas HUS.
REM
REM  Valida los ARCHIVOS PLANOS de la Circular 022/2023 de la ADRES:
REM  FURIPS1, FURIPS2, FURTRAN, FUCTAS y FURCEN. Revisa:
REM   1) La NOMENCLATURA del nombre de cada archivo (prefijo + codigo +
REM      fecha/periodo/hora, con expresion regular).
REM   2) Las REGLAS GENERALES de la Circular: campos separados por coma,
REM      sin comillas, fechas DD/MM/AAAA, numeros sin puntos ni comas,
REM      sin relleno de ceros/espacios, longitudes MAXIMAS.
REM   3) La malla campo a campo de FURIPS 1 (102 campos) y FURIPS 2 (9).
REM  Deja el reporte de errores en JSON y CSV (se abre en Excel):
REM  REPORTE_PLANOS_ADRES_<fecha>.csv / .json
REM
REM  USO:
REM   1) Copie este .cmd JUNTO con validar_planos_adres.py y
REM      validar_furips.py a la carpeta donde estan los TXT.
REM   2) Doble clic. Tambien puede ARRASTRAR una carpeta o un TXT
REM      encima del .cmd.
REM
REM  No instala nada (Python puro) y NO modifica los archivos: solo LEE.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title VALIDAR PLANOS ADRES - Motor Glosas HUS

echo.
echo ============================================================
echo   VALIDAR ARCHIVOS PLANOS - Circular 022/2023 ADRES
echo   (FURIPS1, FURIPS2, FURTRAN, FUCTAS, FURCEN)
echo ============================================================
echo.

set "RUTA=%~1"
if not defined RUTA set "RUTA=%~dp0"
if "%RUTA:~-1%"=="\" set "RUTA=%RUTA:~0,-1%"
echo [i] Ruta a validar: "%RUTA%"
echo.

set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE (
    echo [X] No se encontro Python. Instalelo desde https://www.python.org/downloads/
    echo     marcando la casilla "Add Python to PATH" y vuelva a dar doble clic.
    pause
    exit /b 1
)

if not exist "%~dp0validar_planos_adres.py" (
    echo [X] No encuentro validar_planos_adres.py junto a este .cmd.
    echo     Copie validar_planos_adres.py y validar_furips.py aqui.
    pause
    exit /b 1
)
if not exist "%~dp0validar_furips.py" (
    echo [X] Falta validar_furips.py junto a este .cmd ^(trae la malla de
    echo     campos de la Circular^). Copielo a esta misma carpeta.
    pause
    exit /b 1
)

%PYEXE% "%~dp0validar_planos_adres.py" --ruta "%RUTA%"
echo.
echo ============================================================
echo   Listo. Revise REPORTE_PLANOS_ADRES_*.csv ^(se abre en
echo   Excel^) o el .json en: "%RUTA%"
echo ============================================================
pause
