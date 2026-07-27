@echo off
REM ====================================================================
REM  VALIDAR_FURIPS.cmd  -  Bot de doble clic del Motor Glosas HUS.
REM
REM  Valida los FURIPS 1 y 2 (TXT) contra la malla de la Circular 022
REM  de 2023 de la ADRES y contra los soportes de cada carpeta de
REM  factura (RIPS, CUV, factura XML/PDF, epicrisis) y deja un informe
REM  Excel detallado: INFORME_VALIDACION_FURIPS_AAAAMMDD.xlsx.
REM
REM  USO:
REM   1) Copie este .cmd JUNTO con validar_furips.py (y los demas .py
REM      de la carpeta tools\adres) a la carpeta raiz de las facturas.
REM   2) Doble clic. Tambien puede ARRASTRAR una carpeta encima del
REM      .cmd para validar esa carpeta.
REM
REM  Se instala solo openpyxl y pypdf si faltan. No toca los archivos
REM  originales: solo LEE y genera el Excel.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title VALIDAR FURIPS - Motor Glosas HUS

echo.
echo ============================================================
echo   VALIDAR FURIPS - Circular 022/2023 ADRES + soportes
echo ============================================================
echo.

REM --- 1) Carpeta a procesar: la arrastrada o la del propio .cmd ------
set "CARPETA=%~1"
if not defined CARPETA set "CARPETA=%~dp0"
if "%CARPETA:~-1%"=="\" set "CARPETA=%CARPETA:~0,-1%"
echo [i] Carpeta a validar: "%CARPETA%"
echo.

REM --- 2) Buscar Python (validando por ejecucion) ---------------------
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

REM --- 3) Asegurar openpyxl (Excel) y pypdf (lectura de PDF) ----------
%PYEXE% -c "import openpyxl" >nul 2>&1 || (
    echo [i] Instalando el componente de Excel ^(openpyxl^), espere...
    %PYEXE% -m pip install --quiet --user openpyxl >nul 2>&1
)
%PYEXE% -c "import openpyxl" >nul 2>&1 || (
    echo [X] No se pudo instalar openpyxl. Ejecute a mano:
    echo     %PYEXE% -m pip install openpyxl
    pause
    exit /b 1
)
%PYEXE% -c "import pypdf" >nul 2>&1 || (
    echo [i] Instalando el lector de PDF ^(pypdf^), espere...
    %PYEXE% -m pip install --quiet --user pypdf >nul 2>&1
)
REM pdfplumber lee mejor algunos PDF dificiles; se intenta pero no es
REM obligatorio (si falla la instalacion, el bot corre igual con pypdf).
%PYEXE% -c "import pdfplumber" >nul 2>&1 || (
    echo [i] Instalando lector adicional de PDF ^(pdfplumber^), espere...
    %PYEXE% -m pip install --quiet --user pdfplumber >nul 2>&1
)

REM OCR para PDF escaneados (opcional pero recomendado): si no se puede
REM instalar, el bot corre igual (los escaneados quedan SIN TEXTO).
%PYEXE% -c "import pypdfium2" >nul 2>&1 || (
    echo [i] Instalando el visor de paginas para OCR ^(pypdfium2^), espere...
    %PYEXE% -m pip install --quiet --user pypdfium2 >nul 2>&1
)
%PYEXE% -c "import rapidocr_onnxruntime" >nul 2>&1 || (
    echo [i] Instalando el motor OCR ^(rapidocr-onnxruntime^) para leer PDF
    echo     ESCANEADOS. Descarga ~200 MB SOLO la primera vez. NO cierre la
    echo     ventana: abajo se ve el avance de la descarga...
    %PYEXE% -m pip install --user rapidocr-onnxruntime
)
%PYEXE% -c "import rapidocr_onnxruntime" >nul 2>&1 && (
    echo [i] Lector OCR listo.
) || (
    echo [!] OCR no disponible: se continua igual y los PDF escaneados
    echo     quedaran marcados SIN TEXTO para revision manual.
)

REM --- 4) Correr el bot ----------------------------------------------
if not exist "%~dp0validar_furips.py" (
    echo [X] No encuentro validar_furips.py junto a este .cmd.
    echo     Copie AMBOS archivos a la misma carpeta.
    pause
    exit /b 1
)
%PYEXE% "%~dp0validar_furips.py" --raiz "%CARPETA%"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
    echo ============================================================
    echo   [X] La validacion FALLO ^(codigo %RC%^). NO se genero el Excel.
    echo   Revise los mensajes de arriba. NO radique con este informe.
    echo ============================================================
    pause
    exit /b %RC%
)
echo ============================================================
echo   Listo. Revise el Excel INFORME_VALIDACION_FURIPS_*.xlsx
echo   que quedo en: "%CARPETA%"
echo ============================================================
pause
