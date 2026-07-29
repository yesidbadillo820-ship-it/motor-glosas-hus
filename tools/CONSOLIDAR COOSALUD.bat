@echo off
REM ============================================================================
REM  CONSOLIDAR COOSALUD.bat
REM
REM  Doble clic, o ARRASTRA la carpeta "CARGUE MASIVO COOSALUD" encima de este
REM  .bat. Pide la fecha del dia que se revisa y (opcional) la base DGH, y
REM  genera en <carpeta>\CONSOLIDADOS:
REM     CONSOLIDADO GLOSAS / DETALLE / FACTURAS,
REM     SERVICIOS FACTURADOS COOSALUD (si diste la base) y OBJECIONES.xlsx
REM
REM  Requiere Python 3. La libreria openpyxl se instala sola si falta.
REM  Debe estar junto a consolidar_coosalud.py.
REM ============================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "SCRIPT=%~dp0consolidar_coosalud.py"

REM Elegir el ejecutable de Python disponible.
set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"

REM Instalar openpyxl si falta (solo la primera vez).
"%PYEXE%" -c "import openpyxl" 2>nul || (
    echo   Instalando openpyxl ^(solo la primera vez^)...
    "%PYEXE%" -m pip install openpyxl
)

REM 1) Carpeta arrastrada sobre el .bat -> llega como %1
set "CARPETA=%~1"
if "%CARPETA%"=="" (
    echo.
    echo   Arrastra la carpeta "CARGUE MASIVO COOSALUD" sobre este .bat,
    echo   o pega la ruta aqui abajo y presiona Enter.
    echo   (Enter sin nada = D:\USUARIO CARTERA\Desktop\CARGUE MASIVO COOSALUD)
    echo.
    set /p "CARPETA=  Carpeta: "
)
if "%CARPETA%"=="" set "CARPETA=D:\USUARIO CARTERA\Desktop\CARGUE MASIVO COOSALUD"

REM 2) Fecha del dia que se revisa.
echo.
set /p "FECHA=  Fecha del dia que se revisa (DD/MM/AAAA, ej 04/07/2026): "
if "%FECHA%"=="" (
    echo   Falta la fecha. Cancelado.
    goto :fin
)

REM 3) Base DGH (opcional).
echo.
echo   Base DGH de servicios facturados (opcional):
echo   pega la ruta del archivo, o Enter para seguir sin ella.
set /p "BASE=  Base DGH: "

echo.
echo   Procesando: %CARPETA%
echo.
if "%BASE%"=="" (
    "%PYEXE%" "%SCRIPT%" --carpeta "%CARPETA%" --fecha %FECHA%
) else (
    "%PYEXE%" "%SCRIPT%" --carpeta "%CARPETA%" --fecha %FECHA% --servicios "%BASE%"
)

:fin
echo.
echo ============================================================================
pause
endlocal
