@echo off
rem ================================================================
rem  AUTODEPLOY del Motor de Glosas en modo SIN DOCKER.
rem  Corre cada 5 minutos por tarea programada (la crea el instalador
rem  REVIVIR_EXPRESS_SIN_DOCKER.cmd). Si hay codigo nuevo fusionado en
rem  la rama motor-glosas: lo baja, actualiza dependencias y reinicia
rem  el servidor (su vigilante lo revive solo con el codigo nuevo).
rem  Registro en data\autodeploy.log
rem ================================================================
setlocal
set "BASE=C:\motor-glosas"
set "REPO=%BASE%\repo"
if not exist "%REPO%\.git" exit /b 0
cd /d "%REPO%"
set "LOG=%REPO%\data\autodeploy.log"

git fetch origin motor-glosas >nul 2>&1
if errorlevel 1 (
  echo [%date% %time%] sin internet o sin acceso a GitHub: se reintenta en 5 min >> "%LOG%"
  goto :asegurar
)

for /f %%a in ('git rev-parse HEAD') do set "LOCAL=%%a"
for /f %%a in ('git rev-parse origin/motor-glosas') do set "REMOTO=%%a"
if "%LOCAL%"=="%REMOTO%" goto :asegurar

echo [%date% %time%] codigo nuevo detectado: %REMOTO:~0,7% — aplicando... >> "%LOG%"
git reset --hard origin/motor-glosas >> "%LOG%" 2>&1
rem psycopg2 es solo para PostgreSQL: aca la base es SQLite, se salta
findstr /v /i "psycopg2" "%REPO%\requirements.txt" > "%REPO%\data\requirements_local.txt"
"%REPO%\venv\Scripts\python.exe" -m pip install -r "%REPO%\data\requirements_local.txt" -q >> "%LOG%" 2>&1
rem Reiniciar el servidor: se apaga y su vigilante lo revive renovado.
rem SOLO el de produccion (--port 8080). Antes cerraba cualquier uvicorn
rem de la aplicacion y, como esta tarea corre cada 5 minutos, le mataba
rem el motor de pruebas al auditor sin que entendiera por que se le
rem apagaba solo (revision del 04-08-2026).
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object {$_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >> "%LOG%" 2>&1
echo [%date% %time%] deploy aplicado; se comprueba que vuelva a subir >> "%LOG%"

:asegurar
rem Pase lo que pase, garantizar que servidor y tunel esten corriendo
if exist "%BASE%\arrancar_motor_glosas.cmd" call "%BASE%\arrancar_motor_glosas.cmd"

rem ---------------------------------------------------------------
rem  RED DE SEGURIDAD (20-08-2026).
rem
rem  Esta tarea MATA el motor para aplicar el codigo nuevo, contando
rem  con que el vigilante lo resucite. El vigilante es una ventana de
rem  consola: si alguien la cierra, o la sesion de Windows se cierra,
rem  no queda nadie que lo levante y el hospital se queda SIN PORTAL
rem  hasta que una persona lo note y lo arranque a mano.
rem
rem  Paso tres veces el 20-08 y cada vez fue Yesid quien lo levanto.
rem  Aca se comprueba que de verdad volvio; si no, se arranca directo
rem  sin depender del vigilante.
rem ---------------------------------------------------------------
timeout /t 12 /nobreak >nul
powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; if($p){exit 0}else{exit 1}"
if not errorlevel 1 goto :fin

echo [%date% %time%] el motor NO volvio solo: se arranca directo >> "%LOG%"
cd /d "%REPO%"
start "" /b "%REPO%\venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8080 >> "%LOG%" 2>&1
timeout /t 15 /nobreak >nul
powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; if($p){exit 0}else{exit 1}"
if errorlevel 1 (
  echo [%date% %time%] ALERTA: el motor sigue caido tras arrancarlo directo >> "%LOG%"
) else (
  echo [%date% %time%] motor levantado por la red de seguridad >> "%LOG%"
)

:fin
exit /b 0
