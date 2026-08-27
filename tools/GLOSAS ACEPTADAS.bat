@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Glosas aceptadas - completar respuesta de acta
color 0F

echo.
echo  ============================================================
echo   COMPLETAR RESPUESTA / TRAMITE / ACTA
echo   Consolidado mensual de glosas aceptadas - Auditoria HUS
echo  ============================================================
echo.

rem ---- 1. Buscar Python -------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo  [X] No se encontro Python en este equipo.
  echo.
  echo      Instalelo desde https://www.python.org/downloads/
  echo      IMPORTANTE: marque la casilla "Add Python to PATH".
  echo.
  pause & exit /b 1
)

rem ---- 2. Verificar la libreria de Excel --------------------------------
%PY% -c "import openpyxl" >nul 2>&1
if errorlevel 1 (
  echo  [!] Falta la libreria openpyxl. Instalando ...
  %PY% -m pip install --quiet openpyxl
  if errorlevel 1 ( echo  [X] No se pudo instalar. & pause & exit /b 1 )
  echo  [OK] Instalada.
  echo.
)

rem ---- 3. Tomar los dos archivos ---------------------------------------
set "A=%~1"
set "B=%~2"

if not defined B (
  echo  Seleccione los DOS archivos de Excel.
  echo  ^(tambien puede arrastrarlos sobre este archivo .bat^)
  echo.
  echo  1/2 - Consolidado de GLOSAS ACEPTADAS del mes
  for /f "usebackq delims=" %%F in (`powershell -NoProfile -STA -Command ^
    "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='1/2  Consolidado de GLOSAS ACEPTADAS del mes'; $d.Filter='Excel (*.xlsx;*.xlsm)|*.xlsx;*.xlsm'; if($d.ShowDialog() -eq 'OK'){$d.FileName}"`) do set "A=%%F"
  if not defined A ( echo  Cancelado. & pause & exit /b 1 )
  echo      %A%
  echo.
  echo  2/2 - CIRCULARIZACION DE GLOSAS del ano
  for /f "usebackq delims=" %%F in (`powershell -NoProfile -STA -Command ^
    "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='2/2  CIRCULARIZACION DE GLOSAS del ano'; $d.Filter='Excel (*.xlsx;*.xlsm)|*.xlsx;*.xlsm'; if($d.ShowDialog() -eq 'OK'){$d.FileName}"`) do set "B=%%F"
  if not defined B ( echo  Cancelado. & pause & exit /b 1 )
  echo      %B%
  echo.
)

if not exist "%A%" ( echo  [X] No existe: %A% & pause & exit /b 1 )
if not exist "%B%" ( echo  [X] No existe: %B% & pause & exit /b 1 )

rem ---- 4. Nombres de salida, junto al consolidado -----------------------
set "SALIDA=%~dpn1"
if "%SALIDA%"=="" for %%I in ("%A%") do set "SALIDA=%%~dpnI"
set "XLSX=%SALIDA% - DILIGENCIADO.xlsx"
set "CSV=%SALIDA% - REVISAR.csv"

rem ---- 5. Rehacer? ------------------------------------------------------
echo  Si el archivo YA fue diligenciado antes y quiere volver a generarlo
echo  con las reglas actuales, responda S. Si es la primera vez, responda N.
echo.
set "REH="
set /p "R=  Rehacer las filas de tipo ACTA ya diligenciadas? (S/N) [N]: "
if /i "!R!"=="S" set "REH=--rehacer"
echo.

rem ---- 6. Ejecutar ------------------------------------------------------
echo  Procesando, espere ...
echo  ------------------------------------------------------------
%PY% "%~dp0completar_tramite_glosas_aceptadas.py" "%A%" "%B%" "%XLSX%" "%CSV%" %REH%
set "RC=%errorlevel%"
echo  ------------------------------------------------------------
echo.

if not "%RC%"=="0" (
  echo  [X] Termino con errores. Revise el mensaje de arriba.
  echo.
  pause & exit /b %RC%
)

echo  [OK] Listo.
echo.
echo   Archivo diligenciado :  %XLSX%
echo   Casos a revisar      :  %CSV%
echo.
set /p "V=  Abrir el archivo diligenciado ahora? (S/N) [S]: "
if /i not "!V!"=="N" start "" "%XLSX%"
if exist "%CSV%" (
  set /p "W=  Abrir tambien la lista de casos a revisar? (S/N) [S]: "
  if /i not "!W!"=="N" start "" "%CSV%"
)
echo.
pause
endlocal
