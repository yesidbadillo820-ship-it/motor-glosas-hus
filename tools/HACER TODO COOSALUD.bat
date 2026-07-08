@echo off
REM ============================================================================
REM  HACER TODO COOSALUD.bat  —  TODO EN UNO (organiza + consolida)
REM
REM  Arrastra el ZIP de COOSALUD encima de este .bat (o doble clic y pega la
REM  ruta). Hace los DOS pasos y deja OBJECIONES.xlsx y los consolidados en
REM     D:\USUARIO CARTERA\Desktop\CARGUE MASIVO COOSALUD\CONSOLIDADOS
REM
REM  Guarda todo lo que pasa en  _log_coosalud.txt  (junto a este .bat).
REM  Debe estar junto a organizar_cargue_masivo_coosalud.py y consolidar_coosalud.py.
REM ============================================================================
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "ORGANIZAR=%~dp0organizar_cargue_masivo_coosalud.py"
set "CONSOLIDAR=%~dp0consolidar_coosalud.py"
set "DESTINO=D:\USUARIO CARTERA\Desktop"
set "CARPETA=%DESTINO%\CARGUE MASIVO COOSALUD"
set "LOG=%~dp0_log_coosalud.txt"
echo ===== HACER TODO COOSALUD ===== > "%LOG%"

REM --- Verificar que existen los scripts al lado ---
if not exist "%ORGANIZAR%" (
    echo   ERROR: no encuentro organizar_cargue_masivo_coosalud.py junto a este .bat.
    echo   Asegurate de tener los 2 archivos .py en la MISMA carpeta que este .bat.
    goto :fin
)
if not exist "%CONSOLIDAR%" (
    echo   ERROR: no encuentro consolidar_coosalud.py junto a este .bat.
    goto :fin
)

REM --- Verificar Python ---
set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"
"%PYEXE%" --version >nul 2>nul
if errorlevel 1 (
    echo   ERROR: no encuentro Python. Instalalo desde https://www.python.org/downloads/
    echo   y marca la casilla "Add Python to PATH" al instalar.
    goto :fin
)

REM --- openpyxl ---
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
if not exist "%ZIP%" ( echo   ERROR: no existe el archivo:  %ZIP% & goto :fin )

REM --- Fecha ---
echo.
set /p "FECHA=  Fecha del dia que se revisa (DD/MM/AAAA, ej 08/07/2026): "
if "%FECHA%"=="" ( echo   Falta la fecha. Cancelado. & goto :fin )

REM --- Base DGH (opcional) ---
echo.
echo   Base DGH "SERVICIOS FACTURADOS COOSALUD DGH.xlsx" (opcional).
echo   Pega la ruta, o Enter para seguir sin ella.
set /p "BASE=  Base DGH: "
if not "%BASE%"=="" if not exist "%BASE%" (
    echo   AVISO: no existe esa base DGH, se seguira SIN ella:  %BASE%
    set "BASE="
)

echo.
echo ============================================================================
echo   PASO 1/2 - Organizando el ZIP...
echo ============================================================================
echo [PASO 1] py organizar --zip "%ZIP%" --destino "%DESTINO%" >> "%LOG%"
"%PYEXE%" "%ORGANIZAR%" --zip "%ZIP%" --destino "%DESTINO%" >> "%LOG%" 2>&1
type "%LOG%"
if errorlevel 1 (
    echo   Fallo el paso 1. Mira el detalle en:  %LOG%
    goto :fin
)
if not exist "%CARPETA%" (
    echo   ERROR: no se creo la carpeta esperada:
    echo     %CARPETA%
    echo   Revisa el log:  %LOG%
    goto :fin
)

echo.
echo ============================================================================
echo   PASO 2/2 - Consolidando y generando OBJECIONES...
echo ============================================================================
echo [PASO 2] py consolidar --carpeta "%CARPETA%" --fecha %FECHA% --servicios "%BASE%" >> "%LOG%"
if "%BASE%"=="" (
    "%PYEXE%" "%CONSOLIDAR%" --carpeta "%CARPETA%" --fecha %FECHA% 2>&1 | more
    "%PYEXE%" "%CONSOLIDAR%" --carpeta "%CARPETA%" --fecha %FECHA% >> "%LOG%" 2>&1
) else (
    "%PYEXE%" "%CONSOLIDAR%" --carpeta "%CARPETA%" --fecha %FECHA% --servicios "%BASE%" 2>&1 | more
    "%PYEXE%" "%CONSOLIDAR%" --carpeta "%CARPETA%" --fecha %FECHA% --servicios "%BASE%" >> "%LOG%" 2>&1
)

echo.
if exist "%CARPETA%\CONSOLIDADOS\OBJECIONES.xlsx" (
    echo ============================================================================
    echo   LISTO. Abriendo la carpeta de resultados...
    echo   %CARPETA%\CONSOLIDADOS
    echo ============================================================================
    start "" explorer "%CARPETA%\CONSOLIDADOS"
) else (
    echo   ERROR: no se genero OBJECIONES.xlsx. Mira el detalle en:
    echo     %LOG%
)

:fin
echo.
echo   (Registro guardado en: %LOG%)
pause
endlocal
