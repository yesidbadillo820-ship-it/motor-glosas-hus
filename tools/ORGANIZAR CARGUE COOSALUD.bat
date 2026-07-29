@echo off
REM ============================================================================
REM  ORGANIZAR CARGUE COOSALUD.bat
REM
REM  Doble clic o ARRASTRA el archivo .zip encima de este .bat.
REM  Extrae el ZIP y crea en el Escritorio la carpeta:
REM     D:\USUARIO CARTERA\Desktop\CARGUE MASIVO COOSALUD
REM  con las subcarpetas DETALLES, FACTURAS y GLOSAS.
REM
REM  Requiere Python 3 instalado (el lanzador "py" o "python").
REM ============================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "SCRIPT=%~dp0organizar_cargue_masivo_coosalud.py"

REM Elegir el ejecutable de Python disponible.
set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"

REM 1) ZIP arrastrado sobre el .bat  ->  llega como %1
set "ZIP=%~1"

REM 2) Si no arrastraron nada, pedir la ruta del ZIP.
if "%ZIP%"=="" (
    echo.
    echo   Arrastra el archivo .zip sobre este .bat, o pega la ruta aqui abajo.
    echo.
    set /p "ZIP=  Ruta del ZIP: "
)

if "%ZIP%"=="" (
    echo   No se indico ningun ZIP. Cancelado.
    goto :fin
)

echo.
echo   Procesando: %ZIP%
echo.
"%PYEXE%" "%SCRIPT%" --zip "%ZIP%"

:fin
echo.
echo ============================================================================
pause
endlocal
