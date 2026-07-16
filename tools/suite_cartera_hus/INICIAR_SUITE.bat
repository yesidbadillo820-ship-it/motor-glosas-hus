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

rem --- 3) Abrir la Suite ------------------------------------------
start "" pythonw suite_cartera_hus.py
if errorlevel 1 python suite_cartera_hus.py
exit /b 0
