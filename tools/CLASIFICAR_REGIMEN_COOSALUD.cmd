@echo off
REM ====================================================================
REM  CLASIFICAR_REGIMEN_COOSALUD.cmd - Bot de doble clic del Motor Glosas HUS.
REM
REM  Lee un Excel con la columna FACTURA, busca cada factura en el share
REM  de facturacion electronica, identifica el regimen (Subsidiado o
REM  Contributivo) con el RIPS, copia los soportes completos (XML, PDF,
REM  RIPS, CUV) a la carpeta maestra de su regimen y deja el Excel
REM  AUDITORIA_FECHAS_REGIMEN.xlsx con el cruce de fechas RIPS vs factura.
REM
REM  USO (con la sesion normal, sin permisos especiales):
REM   1) Copie este .cmd + clasificar_regimen_coosalud.py junto al Excel
REM      de facturas (ej. "COOSALUD PARA BRAYAN.xlsx").
REM   2) Doble clic. (Tambien puede ARRASTRAR el Excel encima del .cmd.)
REM   3) Las carpetas Subsidiado\ y Contributivo\ y el Excel de auditoria
REM      quedan en CLASIFICADO_REGIMEN\ junto a este .cmd.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions
title CLASIFICAR REGIMEN COOSALUD - Motor Glosas HUS

set "AQUI=%~dp0"
if "%AQUI:~-1%"=="\" set "AQUI=%AQUI:~0,-1%"
set "DESTINO=%AQUI%\CLASIFICADO_REGIMEN"

echo.
echo ============================================================
echo   CLASIFICAR POR REGIMEN + CRUCE DE FECHAS (COOSALUD)
echo ============================================================
echo.

REM --- Excel de facturas: el arrastrado o el primero *.xlsx de aqui ----
set "EXCEL=%~1"
if not defined EXCEL for %%F in ("%AQUI%\*BRAYAN*.xlsx") do if not defined EXCEL set "EXCEL=%%~fF"
if not defined EXCEL for %%F in ("%AQUI%\*.xlsx") do if not defined EXCEL set "EXCEL=%%~fF"
if not defined EXCEL (
    echo [X] No encontre ningun .xlsx junto a este .cmd.
    echo     Copie el Excel de facturas aqui o arrastrelo encima del .cmd.
    pause
    exit /b 1
)
echo   Excel de facturas: "%EXCEL%"
echo   Destino:           "%DESTINO%"
echo.

REM --- Python -----------------------------------------------------------
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE (
    echo [X] No se encontro Python. Instalelo de https://www.python.org/downloads/
    echo     marcando "Add Python to PATH" y reintente.
    pause
    exit /b 1
)
%PYEXE% -c "import openpyxl" >nul 2>&1 || (
    echo [i] Instalando el componente de Excel ^(openpyxl^), espere...
    %PYEXE% -m pip install --quiet --user openpyxl >nul 2>&1
)

if not exist "%AQUI%\clasificar_regimen_coosalud.py" (
    echo [X] Falta clasificar_regimen_coosalud.py junto a este .cmd.
    pause
    exit /b 1
)
%PYEXE% "%AQUI%\clasificar_regimen_coosalud.py" --excel "%EXCEL%" --destino "%DESTINO%"
echo.
echo ============================================================
echo   Listo. Revise AUDITORIA_FECHAS_REGIMEN.xlsx y las carpetas
echo   Subsidiado\ y Contributivo\ dentro de CLASIFICADO_REGIMEN\.
echo ============================================================
pause
