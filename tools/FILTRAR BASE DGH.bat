@echo off
REM ============================================================================
REM  FILTRAR BASE DGH.bat — deja la base DGH reducida a las facturas del lote,
REM  para poder moverla o subirla (la original pesa ~70 MB).
REM  Acepta hasta 4 bases: si el export de DGH no cabe en un solo Excel hay que
REM  bajarlo por tandas (por rango de fechas) y darlas todas aqui.
REM  No usa etiquetas ni GOTO a proposito: estos .bat viajan con finales de
REM  linea de Unix y los saltos se vuelven impredecibles en Windows.
REM ============================================================================
@chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"

REM Librerias que necesita el bot. openpyxl lee/escribe .xlsx; pyxlsb lee los
REM .xlsb (Excel binario), que es como DGH exporta la base de servicios.
"%PYEXE%" -c "import openpyxl" 2>nul || "%PYEXE%" -m pip install --quiet openpyxl
"%PYEXE%" -c "import pyxlsb" 2>nul || "%PYEXE%" -m pip install --quiet pyxlsb

echo.
echo   Arrastra los archivos a la ventana (no hace falta escribir la ruta).
echo   Cuando no tengas mas bases que agregar, solo pulsa Enter.
echo.

set "BASES="

set "B1=%~1"
if "%B1%"=="" set /p B1="  1) Base DGH (SERVICIOS FACTURADOS COOSALUD DGH.xlsx): "
set "B1=%B1:"=%"
if not "%B1%"=="" set BASES=%BASES% "%B1%"

set "B2="
set /p B2="  2) Otra base/tanda (Enter si no hay mas): "
set "B2=%B2:"=%"
if not "%B2%"=="" set BASES=%BASES% "%B2%"

set "B3="
if not "%B2%"=="" set /p B3="  3) Otra base/tanda (Enter si no hay mas): "
set "B3=%B3:"=%"
if not "%B3%"=="" set BASES=%BASES% "%B3%"

set "B4="
if not "%B3%"=="" set /p B4="  4) Otra base/tanda (Enter si no hay mas): "
set "B4=%B4:"=%"
if not "%B4%"=="" set BASES=%BASES% "%B4%"

if not defined BASES echo   No indicaste ninguna base. & pause & exit /b 1

echo.
echo   Como quieres indicar las facturas del lote?
echo     1 = arrastrando la carpeta CARGUE MASIVO COOSALUD
echo     2 = arrastrando un TXT con una factura por linea
set "SEL="
set /p SEL="  Opcion [1]: "
set "PORLISTA="
if "%SEL%"=="2" set "PORLISTA=1"

set "RUTA="
if defined PORLISTA set /p RUTA="  Arrastra aqui el TXT con las facturas: "
if not defined PORLISTA set /p RUTA="  Arrastra aqui la carpeta CARGUE MASIVO COOSALUD: "
set "RUTA=%RUTA:"=%"
if "%RUTA%"=="" echo   No indicaste las facturas del lote. & pause & exit /b 1

echo.
if defined PORLISTA "%PYEXE%" "%~dp0filtrar_base_dgh.py" %BASES% --lista "%RUTA%" --salida "%~dp0BASE_DGH_FILTRADA.xlsx"
if not defined PORLISTA "%PYEXE%" "%~dp0filtrar_base_dgh.py" %BASES% --carpeta "%RUTA%" --salida "%~dp0BASE_DGH_FILTRADA.xlsx"
echo.
pause
