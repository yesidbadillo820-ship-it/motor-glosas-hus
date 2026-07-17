@echo off
REM ====================================================================
REM  INFORME_BAJA_CARTERA.cmd  -  Bot de doble clic del Motor Glosas HUS.
REM
REM  Genera el INFORME WORD del area de facturacion con las facturas que
REM  NO cumplen los parametros de la Resolucion 577 del 16/10/2019
REM  (manual de cartera) para entregar a cartera, para su tramite de
REM  depuracion / baja. Lee el PDF UNIDO (_UNIDO_*.pdf o su copia .cmd
REM  que deja el bot UNIR_PDFS) de cada carpeta de factura, extrae el
REM  valor y el INFORME DE TRABAJO SOCIAL, ordena de la mas cara a la
REM  mas economica y concluye cada factura una a una.
REM
REM  USO:
REM   1) Corra primero UNIR_PDFS.cmd en la carpeta de las facturas.
REM   2) Copie este .cmd JUNTO con generar_informe_baja_cartera.py a la
REM      carpeta raiz de las facturas y dele doble clic. Tambien puede
REM      ARRASTRAR una carpeta encima del .cmd.
REM
REM  Se instala solo python-docx y pypdf si faltan. Solo LEE los PDF;
REM  no modifica nada. El Word queda como INFORME_BAJA_CARTERA_*.docx.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title INFORME BAJA CARTERA - Motor Glosas HUS

echo.
echo ============================================================
echo   INFORME BAJA CARTERA - Resolucion 577/2019 (Word)
echo ============================================================
echo.

set "CARPETA=%~1"
if not defined CARPETA set "CARPETA=%~dp0"
if "%CARPETA:~-1%"=="\" set "CARPETA=%CARPETA:~0,-1%"
echo [i] Carpeta a procesar: "%CARPETA%"
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

%PYEXE% -c "import docx" >nul 2>&1 || (
    echo [i] Instalando el componente de Word ^(python-docx^), espere...
    %PYEXE% -m pip install --quiet --user python-docx >nul 2>&1
)
%PYEXE% -c "import docx" >nul 2>&1 || (
    echo [X] No se pudo instalar python-docx. Ejecute a mano:
    echo     %PYEXE% -m pip install python-docx
    pause
    exit /b 1
)
%PYEXE% -c "import pypdf" >nul 2>&1 || %PYEXE% -c "import pdfplumber" >nul 2>&1 || (
    echo [i] Instalando el lector de PDF ^(pypdf^), espere...
    %PYEXE% -m pip install --quiet --user pypdf >nul 2>&1
)

if not exist "%~dp0generar_informe_baja_cartera.py" (
    echo [X] No encuentro generar_informe_baja_cartera.py junto a este .cmd.
    echo     Copie AMBOS archivos a la misma carpeta.
    pause
    exit /b 1
)
%PYEXE% "%~dp0generar_informe_baja_cartera.py" --raiz "%CARPETA%"
echo.
echo ============================================================
echo   Listo. Revise el Word INFORME_BAJA_CARTERA_*.docx que
echo   quedo en: "%CARPETA%"
echo   OJO: las facturas SIN informe de trabajo social quedan con
echo   NOTA DE REVISION dentro del documento - completelas antes
echo   de presentar el informe.
echo ============================================================
pause
