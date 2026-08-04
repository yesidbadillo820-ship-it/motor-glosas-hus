@echo off
REM ====================================================================
REM  COMPLETAR_INFORME_XML.cmd - Bot de doble clic del Motor Glosas HUS.
REM
REM  Completa el informe Excel de revision XML (devoluciones DE4401):
REM  busca el XML DIAN (y JSON) de cada factura, analiza CUFE, firma,
REM  acuse DIAN, NUMERO_CONTRATO y COBERTURA_PLAN_BENEFICIOS del sector
REM  salud, y llena VALOR (XML), VALIDACION DIAN, CONCLUSION (ARGUMENTO
REM  GLOSA), ARCHIVO XML y RESPUESTA DGH. Deja un Excel _COMPLETO con
REM  semaforo y hoja RESUMEN.
REM
REM  USO:
REM   1) Copie este .cmd + completar_informe_xml_dian.py junto al Excel
REM      del informe (INFORME_REVISION_XML*.xlsx).
REM   2) Doble clic. (Tambien puede ARRASTRAR el Excel encima del .cmd.)
REM   3) Si la ruta de las facturas cambia, edite la linea RUTA_FACTURAS.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions
title COMPLETAR INFORME XML (DE4401) - Motor Glosas HUS

REM --- CONFIGURACION: ruta donde estan los XML de las facturas --------
set "RUTA_FACTURAS=\\172.16.32.83\factura_electronica_net22\202607\FACTURAS_SALUD"

set "AQUI=%~dp0"
if "%AQUI:~-1%"=="\" set "AQUI=%AQUI:~0,-1%"

echo.
echo ============================================================
echo   COMPLETAR INFORME XML - devoluciones DE4401
echo ============================================================
echo   Facturas (XML): "%RUTA_FACTURAS%"
echo.

REM --- Excel a completar: el arrastrado o el primero INFORME*XML*.xlsx
set "EXCEL=%~1"
if not defined EXCEL for %%F in ("%AQUI%\INFORME*XML*.xlsx") do if not defined EXCEL set "EXCEL=%%~fF"
if not defined EXCEL for %%F in ("%AQUI%\*.xlsx") do if not defined EXCEL set "EXCEL=%%~fF"
if not defined EXCEL (
    echo [X] No encontre ningun .xlsx junto a este .cmd.
    echo     Copie el informe aqui o arrastrelo encima del .cmd.
    pause
    exit /b 1
)
echo   Excel a completar: "%EXCEL%"
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

if not exist "%AQUI%\completar_informe_xml_dian.py" (
    echo [X] Falta completar_informe_xml_dian.py junto a este .cmd.
    pause
    exit /b 1
)
%PYEXE% "%AQUI%\completar_informe_xml_dian.py" --excel "%EXCEL%" --facturas "%RUTA_FACTURAS%"
echo.
echo ============================================================
echo   Listo. Revise el archivo *_COMPLETO.xlsx junto al informe.
echo ============================================================
pause
