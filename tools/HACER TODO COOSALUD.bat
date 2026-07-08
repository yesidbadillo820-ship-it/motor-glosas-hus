@echo off
REM ============================================================================
REM  HACER TODO COOSALUD.bat  —  TODO EN UNO
REM
REM  Arrastra el ZIP de COOSALUD encima de este .bat (o doble clic y pega la
REM  ruta). Hace los DOS pasos seguidos:
REM     1) Organiza el ZIP en  D:\USUARIO CARTERA\Desktop\CARGUE MASIVO COOSALUD
REM        (DETALLES / FACTURAS / GLOSAS, en lotes de 300)
REM     2) Consolida y genera, en esa carpeta \CONSOLIDADOS:
REM        CONSOLIDADO GLOSAS / DETALLE / FACTURAS,
REM        SERVICIOS FACTURADOS COOSALUD (si diste la base DGH) y OBJECIONES.xlsx
REM
REM  Requiere Python 3. openpyxl se instala solo la primera vez.
REM  Debe estar junto a organizar_cargue_masivo_coosalud.py y consolidar_coosalud.py.
REM ============================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "ORGANIZAR=%~dp0organizar_cargue_masivo_coosalud.py"
set "CONSOLIDAR=%~dp0consolidar_coosalud.py"
set "DESTINO=D:\USUARIO CARTERA\Desktop"
set "CARPETA=%DESTINO%\CARGUE MASIVO COOSALUD"

set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"

"%PYEXE%" -c "import openpyxl" 2>nul || (
    echo   Instalando openpyxl ^(solo la primera vez^)...
    "%PYEXE%" -m pip install openpyxl
)

REM --- ZIP (arrastrado como %1, o se pide) ---
set "ZIP=%~1"
if "%ZIP%"=="" (
    echo.
    echo   Arrastra el ZIP de COOSALUD sobre este .bat, o pega la ruta:
    set /p "ZIP=  Ruta del ZIP: "
)
if "%ZIP%"=="" ( echo   No se indico ningun ZIP. Cancelado. & goto :fin )

REM --- Fecha del dia que se revisa ---
echo.
set /p "FECHA=  Fecha del dia que se revisa (DD/MM/AAAA, ej 08/07/2026): "
if "%FECHA%"=="" ( echo   Falta la fecha. Cancelado. & goto :fin )

REM --- Base DGH (opcional) ---
echo.
echo   Base DGH "SERVICIOS FACTURADOS COOSALUD DGH.xlsx" (opcional pero
echo   recomendada: sin ella SLNSERPRO sale del codigo del detalle).
echo   Pega la ruta, o Enter para seguir sin ella.
set /p "BASE=  Base DGH: "

echo.
echo ============================================================================
echo   PASO 1/2 - Organizando el ZIP...
echo ============================================================================
"%PYEXE%" "%ORGANIZAR%" --zip "%ZIP%" --destino "%DESTINO%"
if errorlevel 1 ( echo   Fallo el paso 1. & goto :fin )

echo.
echo ============================================================================
echo   PASO 2/2 - Consolidando y generando OBJECIONES...
echo ============================================================================
if "%BASE%"=="" (
    "%PYEXE%" "%CONSOLIDAR%" --carpeta "%CARPETA%" --fecha %FECHA%
) else (
    "%PYEXE%" "%CONSOLIDAR%" --carpeta "%CARPETA%" --fecha %FECHA% --servicios "%BASE%"
)

echo.
echo ============================================================================
echo   LISTO. Resultados en:
echo   %CARPETA%\CONSOLIDADOS
echo   (OBJECIONES.xlsx + los consolidados). Revisa la hoja NO_CRUZADOS.
echo ============================================================================

:fin
echo.
pause
endlocal
