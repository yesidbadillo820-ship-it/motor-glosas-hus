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
rem Si el registro pasa de ~5 MB se reinicia, para no llenar el disco.
if exist "%LOG%" for %%s in ("%LOG%") do if %%~zs GTR 5000000 del "%LOG%" >nul 2>&1

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
rem  ESPERAS CON PING, NO CON TIMEOUT (21-08-2026). Estos bots ahora
rem  corren tambien SIN sesion iniciada (tarea de arranque del PC), y
rem  ahi `timeout` no siempre tiene una consola de verdad: contesta
rem  "Input redirection is not supported" y sigue de largo sin esperar,
rem  con lo que el bucle se vuelve loco. `ping` a uno mismo espera
rem  igual y funciona en todos los casos. ping -n 6 = 5 segundos.
ping -n 13 127.0.0.1 >nul
powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; if($p){exit 0}else{exit 1}"
if not errorlevel 1 goto :fin

echo [%date% %time%] el motor NO volvio solo: se arranca directo >> "%LOG%"
cd /d "%REPO%"
rem  SE SUELTA EL PROCESO A PROPOSITO (21-08-2026, noche). Antes era
rem  `start /b ... >> %LOG%`, y eso trajo dos desastres encadenados:
rem
rem   1. `/b` no abre ventana nueva, asi que el motor HEREDA la salida
rem      de esta tarea. Windows da la tarea por terminada solo cuando
rem      nadie mas tiene esa salida abierta... y el motor no la suelta
rem      nunca. La tarea se quedaba 'corriendo' para siempre, Windows
rem      terminaba matandola (resultado 255) y, como esta puesta en no
rem      abrir dos a la vez, SALTABA TODAS LAS PASADAS SIGUIENTES. El
rem      autodespliegue dejo de bajar codigo durante horas sin avisar.
rem   2. Como heredaba la salida, el registro del autodespliegue se
rem      llenaba de las lineas de cada visita a la pagina, tapando los
rem      mensajes propios. Justo el archivo donde habia que mirar para
rem      entender por que no bajaba nada.
rem
rem  Ahora se abre en su propia ventana (`cmd /s /c`, que ademas es la
rem  forma segura de pasar comillas dentro de comillas) y escribe en
rem  servidor.log, que es donde va lo del servidor. Esta tarea termina
rem  enseguida y la siguiente pasada corre normal.
start "MotorGlosasRescate" /min cmd /s /c ""%REPO%\venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8080 >> "%REPO%\data\servidor.log" 2>&1"
ping -n 16 127.0.0.1 >nul
powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; if($p){exit 0}else{exit 1}"
if errorlevel 1 (
  echo [%date% %time%] ALERTA: el motor sigue caido tras arrancarlo directo >> "%LOG%"
) else (
  echo [%date% %time%] motor levantado por la red de seguridad >> "%LOG%"
)

:fin
exit /b 0
