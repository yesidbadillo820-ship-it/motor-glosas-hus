@echo off
REM ====================================================================
REM  VALIDADOR_ADRES_WEB.cmd - App web del Validador ADRES (FURIPS).
REM
REM  Levanta el servidor web local y abre el navegador. Desde ahi se
REM  suben los TXT FURIPS 1/2 y el ZIP de soportes, se ve el tablero
REM  con semaforo por factura y se descarga el informe Excel.
REM
REM  USO: doble clic. Requiere que la carpeta validador-adres\ este
REM  junto a la carpeta tools\ del Motor Glosas (estructura del repo).
REM  Se instalan solas las dependencias si faltan. Para compartir en la
REM  red del hospital: otros PC pueden entrar a http://ESTE-PC:8010
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions
title VALIDADOR ADRES WEB - Motor Glosas HUS
cd /d "%~dp0"

set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE (
    echo [X] No se encontro Python. Instalelo desde https://www.python.org/downloads/
    echo     marcando "Add Python to PATH" y vuelva a intentar.
    pause
    exit /b 1
)

echo [i] Verificando dependencias (primera vez puede tardar)...
%PYEXE% -c "import fastapi, uvicorn, multipart, openpyxl" >nul 2>&1 || (
    %PYEXE% -m pip install --quiet --user -r requirements.txt
)
%PYEXE% -c "import fastapi, uvicorn, multipart, openpyxl" >nul 2>&1 || (
    echo [X] No se pudieron instalar las dependencias. Ejecute a mano:
    echo     %PYEXE% -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   VALIDADOR ADRES WEB  -  http://localhost:8010
echo   (deje esta ventana abierta; Ctrl+C para detener)
echo ============================================================
start "" http://localhost:8010
%PYEXE% -m uvicorn app:app --host 0.0.0.0 --port 8010
pause
