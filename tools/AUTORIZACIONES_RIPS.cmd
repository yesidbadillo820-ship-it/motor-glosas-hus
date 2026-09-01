@echo off
REM ====================================================================
REM  AUTORIZACIONES_RIPS.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Busca los numeros de AUTORIZACION dentro de los RIPS en JSON
REM  (Res. 2275/2023) y saca INFORME_AUTORIZACIONES_RIPS.xlsx con:
REM    - que autorizacion trae cada factura y en cuantos servicios,
REM    - los servicios que van SIN autorizacion (null, vacio o "null"),
REM    - los que traen OTRO numero distinto al de la factura.
REM
REM  Acepta un .json, una CARPETA (recorre TODAS las subcarpetas) o un
REM  .zip. Sirve una ruta del servidor de facturacion, por ejemplo:
REM    \\\\172.17.48.7\\Envios\\...\\RIPS\\2026\\07.JULIO\\HUS544245\\RIPS
REM
REM  Se instala solo lo que falte. USO: arrastre la carpeta encima, o
REM  doble clic y pegue la ruta cuando la pida.
REM ====================================================================
chcp 65001 >/dev/null 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title AUTORIZACIONES EN RIPS - Motor Glosas HUS
cd /d "%~dp0"

echo.
echo ============================================================
echo   AUTORIZACIONES EN RIPS JSON  --^>  informe Excel
echo   Motor Glosas HUS - Area de Cartera
echo ============================================================
echo.

where python >/dev/null 2>nul
if errorlevel 1 (
    echo [X] Python no esta instalado.
    echo     Descarguelo de https://www.python.org/downloads/
    echo     IMPORTANTE: marque "Add Python to PATH" al instalar.
    echo.
    pause
    exit /b 1
)

python -c "import openpyxl" >/dev/null 2>nul
if errorlevel 1 (
    echo Instalando componentes por primera vez ^(requiere internet^)...
    python -m pip install --quiet openpyxl
)

set "RUTA=%~1"
if "%RUTA%"=="" (
    echo   Arrastre hasta esta ventana el .json, la CARPETA de RIPS o el
    echo   .zip, y pulse Enter. Tambien puede pegar una ruta del servidor.
    echo.
    set /p "RUTA=  Ruta: "
)

if "%RUTA%"=="" (
    echo.
    echo [X] No indico ninguna ruta.
    pause
    exit /b 1
)

echo.
python "%~dp0autorizaciones_rips.py" "%RUTA%"
set "SALIDA=%ERRORLEVEL%"
echo.
if not "%SALIDA%"=="0" (
    echo [X] El informe no se pudo generar. Revise el mensaje de arriba.
) else (
    echo [OK] Listo. El informe quedo junto a este archivo.
)
echo.
pause
endlocal
