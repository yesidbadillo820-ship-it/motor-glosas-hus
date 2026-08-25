@echo off
REM ============================================================================
REM  FILTRAR BASE DGH.bat — deja la base DGH reducida a las facturas del lote,
REM  para poder moverla o subirla (la original pesa ~70 MB).
REM  Acepta VARIAS bases: si el export de DGH no cabe en un solo Excel hay que
REM  bajarlo por tandas (por rango de fechas) y pasarlas todas aqui.
REM ============================================================================
@chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"

set "BASES=%~1"
if "%BASES%"=="" set /p BASES="  Arrastra aqui la base SERVICIOS FACTURADOS COOSALUD DGH.xlsx: "

:MASBASES
set "OTRA="
set /p OTRA="  Otra base/tanda (Enter si no hay mas): "
if "%OTRA%"=="" goto LOTE
set "BASES=%BASES% %OTRA%"
goto MASBASES

:LOTE
echo.
echo   Como quieres indicar las facturas del lote?
echo     1 = arrastrando la carpeta CARGUE MASIVO COOSALUD
echo     2 = arrastrando un TXT con una factura por linea
set /p OPCION="  Opcion [1]: "
if "%OPCION%"=="2" goto PORLISTA

set /p CARPETA="  Arrastra aqui la carpeta CARGUE MASIVO COOSALUD del lote: "
"%PYEXE%" "%~dp0filtrar_base_dgh.py" %BASES% --carpeta %CARPETA% --salida "%~dp0BASE_DGH_FILTRADA.xlsx"
goto FIN

:PORLISTA
set /p LISTA="  Arrastra aqui el TXT con las facturas: "
"%PYEXE%" "%~dp0filtrar_base_dgh.py" %BASES% --lista %LISTA% --salida "%~dp0BASE_DGH_FILTRADA.xlsx"

:FIN
echo.
pause
