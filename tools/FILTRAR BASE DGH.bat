@echo off
REM ============================================================================
REM  FILTRAR BASE DGH.bat — deja la base DGH reducida a las facturas del lote,
REM  para poder moverla o subirla (la original pesa ~70 MB).
REM  Pide la base y la carpeta "CARGUE MASIVO COOSALUD" del lote.
REM ============================================================================
@chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"
set "BASE=%~1"
if "%BASE%"=="" set /p BASE="  Arrastra aqui la base SERVICIOS FACTURADOS COOSALUD DGH.xlsx: "
set /p CARPETA="  Arrastra aqui la carpeta CARGUE MASIVO COOSALUD del lote: "
"%PYEXE%" "%~dp0filtrar_base_dgh.py" %BASE% --carpeta %CARPETA% --salida "%~dp0BASE_DGH_FILTRADA.xlsx"
echo.
pause
