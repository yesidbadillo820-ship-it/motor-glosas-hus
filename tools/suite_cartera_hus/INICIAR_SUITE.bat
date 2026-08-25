@echo off
chcp 65001 >nul
title Suite Cartera HUS
cd /d "%~dp0"

echo ============================================
echo    SUITE CARTERA HUS  -  Menu unico
echo    Radicacion - Glosas - Cruces masivos
echo ============================================
echo.

rem --- 1) Verificar Python ---------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python no esta instalado en este equipo.
    echo     Descarguelo de https://www.python.org/downloads/
    echo     Durante la instalacion marque "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

rem --- 2) Instalar lo que falte (solo la primera vez) -------------
python -c "import pandas, openpyxl, docx, fitz, pdf2docx, pdfplumber, pptx" >nul 2>nul
if errorlevel 1 (
    echo Instalando componentes por primera vez ^(requiere internet^)...
    python -m pip install --quiet --disable-pip-version-warning pandas openpyxl python-docx pymupdf pdf2docx pdfplumber python-pptx
    if errorlevel 1 (
        echo.
        echo [!] No se pudieron instalar los componentes ^(sin internet?^).
        echo     La Suite abrira igual: la ficha de entidades y los bots
        echo     funcionan; los cruces pediran instalar pandas despues.
        echo.
    )
)

rem --- 2b) Lector de correos .msg (relacion de pagos) --------------
rem     extract-msg declara como dependencia obligatoria "red-black-tree-mod",
rem     que NO instala en Windows/PyPI moderno ^(instalador heredado
rem     incompatible^). Esa pieza solo hace falta para RE-ESCRIBIR .msg; esta
rem     Suite solo los LEE, asi que se instala extract-msg SIN esa dependencia
rem     y se completan sus demas piezas reales por separado.
python -c "import extract_msg" >nul 2>nul
if errorlevel 1 (
    echo Instalando lector de correos .msg por primera vez ^(requiere internet^)...
    python -m pip install --quiet --disable-pip-version-warning --no-deps extract-msg
    python -m pip install --quiet --disable-pip-version-warning olefile beautifulsoup4 compressed-rtf ebcdic RTFDE tzlocal
    if errorlevel 1 (
        echo.
        echo [!] No se pudo instalar el lector de correos .msg ^(sin internet?^).
        echo     El resto de la Suite abrira igual; el boton "Correos de Pagos
        echo     -^> Excel" avisara con instrucciones si hace falta.
        echo.
    )
)

rem --- 3) Abrir la Suite ------------------------------------------
start "" pythonw suite_cartera_hus.py
if errorlevel 1 python suite_cartera_hus.py
exit /b 0
