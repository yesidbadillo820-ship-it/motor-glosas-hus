@echo off
REM ============================================================================
REM  LISTA FACTURAS YA EN TRAMITES.bat — arrastra la carpeta con los MASIVO ya
REM  enviados a sistemas y genera "FACTURAS YA EN TRAMITES.txt", para que el
REM  proximo cargue de tramites no repita facturas.
REM ============================================================================
@chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"
set "CARPETA=%~1"
if "%CARPETA%"=="" set /p CARPETA="  Arrastra aqui la carpeta con los MASIVO enviados y presiona Enter: "
"%PYEXE%" "%~dp0facturas_ya_en_tramites.py" "%CARPETA%" --salida "%~dp0FACTURAS YA EN TRAMITES.txt"
echo.
pause
