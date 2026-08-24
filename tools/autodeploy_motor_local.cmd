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

rem ---------------------------------------------------------------
rem  UNA SOLA PASADA A LA VEZ (24-08-2026).
rem
rem  El registro del PC de cartera mostro 'codigo nuevo detectado'
rem  DOS VECES con medio segundo de diferencia: dos pasadas corriendo
rem  al tiempo. Eso es grave, porque cada una apaga el motor contando
rem  con revivirlo, y entre las dos lo dejan caido: una lo levanta y
rem  la otra lo vuelve a matar.
rem
rem  Se usa un archivo como candado y NO una cuenta de procesos: eso
rem  ultimo ya se intento en el vigilante y salio mal -la orden que
rem  contaba se contaba a si misma y dejo el hospital sin portal-.
rem
rem  Caduca a los 30 minutos: si una pasada muere sin borrarlo, el
rem  autodespliegue no puede quedarse bloqueado esperando a un muerto.
rem ---------------------------------------------------------------
set "CANDADO=%REPO%\data\autodeploy.lock"
if not exist "%CANDADO%" goto :tomar_candado
call :candado_caducado
if not errorlevel 1 goto :tomar_candado
echo [%date% %time%] otra pasada sigue trabajando: esta se salta >> "%LOG%"
exit /b 0
:tomar_candado
echo %date% %time% > "%CANDADO%"

rem ---------------------------------------------------------------
rem  ENCONTRAR GIT (22-08-2026).
rem
rem  Una tarea programada NO hereda el camino de busqueda del
rem  usuario: arranca con un entorno minimo. Si git se instalo solo
rem  para el usuario, o el camino se puso despues de crear la tarea,
rem  aqui adentro `git` sencillamente NO EXISTE.
rem
rem  Lo grave no es que falle: es que fallaba EN SILENCIO. El bot
rem  anotaba una linea de 'sin internet' y seguia de largo, asi que
rem  el PC se quedaba con la version vieja para siempre y todo se
rem  veia bien. Paso el 21-08: cuatro correcciones ya publicadas no
rem  llegaron al hospital y nadie se entero hasta que alguien miro.
rem ---------------------------------------------------------------
rem  Se AGREGA la carpeta de git al camino de busqueda, en vez de
rem  guardar la ruta completa: una ruta con espacios -Program Files-
rem  metida dentro de un `for /f` es un sitio clasico de errores en
rem  los .cmd de Windows. Asi las ordenes de abajo quedan igual que
rem  siempre y no hay comillas que se puedan partir mal.
where git >nul 2>&1 && goto :hay_git
if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "PATH=%PATH%;%ProgramFiles(x86)%\Git\cmd"
if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Git\cmd"
where git >nul 2>&1 && goto :hay_git
echo [%date% %time%] NO SE ENCUENTRA GIT: el PC se va a quedar con la version vieja. Instale Git o agreguelo al PATH del sistema. >> "%LOG%"
goto :asegurar
:hay_git

echo [%date% %time%] revisando si hay codigo nuevo... >> "%LOG%"
git fetch origin motor-glosas >nul 2>&1
if errorlevel 1 (
  echo [%date% %time%] NO SE PUDO CONSULTAR GITHUB: el PC se queda con la version que tiene. Se reintenta en 5 min. >> "%LOG%"
  goto :asegurar
)

for /f %%a in ('git rev-parse HEAD') do set "LOCAL=%%a"
for /f %%a in ('git rev-parse origin/motor-glosas') do set "REMOTO=%%a"
if "%LOCAL%"=="%REMOTO%" goto :asegurar

rem ---------------------------------------------------------------
rem  NO TUMBARLE LA PAGINA A LAS GESTORAS (24-08-2026).
rem
rem  Pedido de Yesid, textual: «necesito que cada vez que hagamos
rem  cambios y demas no se les este cayendo la pagina a los gestores
rem  a cada rato».
rem
rem  Aplicar el codigo nuevo obliga a apagar el motor y volverlo a
rem  levantar: entre 15 y 30 segundos de pagina caida, y lo que
rem  estuviera a medio hacer se pierde -un dictamen que la IA estaba
rem  redactando se va con el motor-.
rem
rem  Entonces se pregunta primero. Si hay alguien trabajando, no se
rem  toca NADA -ni siquiera se baja el codigo, porque dejar el motor
rem  viejo con los archivos de pantalla nuevos rompe cosas- y se
rem  reintenta en 5 minutos. En una oficina de tres personas siempre
rem  aparece un hueco.
rem
rem  DOS SALIDAS PARA QUE NUNCA SE QUEDE ATASCADO:
rem   - Si el motor no contesta, se aplica de una: no hay a quien
rem     interrumpir.
rem   - Si lleva mas de una hora esperando, se aplica igual. Una
rem     correccion urgente no puede quedarse fuera todo el dia.
rem ---------------------------------------------------------------
set "ESPERA=%REPO%\data\deploy_aplazado.txt"
set "OCUPADO="
for /f "usebackq delims=" %%O in (`powershell -NoProfile -Command "try{$r=Invoke-RestMethod -Uri 'http://127.0.0.1:8080/sistema/ocupacion' -TimeoutSec 5; if($r.hay_gente_trabajando){'SI'}else{'NO'}}catch{'SINMOTOR'}"`) do set "OCUPADO=%%O"

if "%OCUPADO%"=="SI" (
  if not exist "%ESPERA%" echo %date% %time% > "%ESPERA%"
  call :aplazar_o_seguir
  if errorlevel 1 goto :asegurar
)
if exist "%ESPERA%" del "%ESPERA%" >nul 2>&1

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
rem  Se le pide al motor que se cierre, y solo si no hace caso en 8
rem  segundos se le fuerza. Asi lo que estuviera contestando en ese
rem  momento alcanza a terminar en vez de cortarse a la mitad.
powershell -NoProfile -Command "$ps=Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object {$_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; foreach($p in $ps){ Stop-Process -Id $p.ProcessId -ErrorAction SilentlyContinue }; Start-Sleep -Seconds 8; foreach($p in $ps){ if(Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue){ Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } }" >> "%LOG%" 2>&1
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
rem ---------------------------------------------------------------
rem  ESPERAR PREGUNTANDO, NO UN TIEMPO FIJO (24-08-2026).
rem
rem  Antes se esperaban 12 segundos y se preguntaba UNA vez. El motor
rem  del hospital carga una base de 133 MB y tarda mas que eso, asi
rem  que se daba por muerto estando vivo... y se arrancaba un SEGUNDO
rem  motor encima del que estaba subiendo. Los dos peleaban por el
rem  mismo puerto y el registro decia 'ALERTA: el motor sigue caido'
rem  con el portal funcionando. Paso el 24-08 a las 9:22.
rem
rem  Ahora se pregunta cada 3 segundos hasta 90. Si sube en 10, se
rem  sigue en 10: no se pierde tiempo. Y si de verdad no sube, se
rem  entera despues de un plazo que si le alcanza.
rem ---------------------------------------------------------------
set /a INTENTOS=0
:esperar_que_suba
powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process | Where-Object {$_.Name -like 'python*' -and $_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; if($p){exit 0}else{exit 1}"
if not errorlevel 1 goto :fin
set /a INTENTOS+=1
if %INTENTOS% GEQ 30 goto :no_subio_solo
ping -n 4 127.0.0.1 >nul
goto :esperar_que_suba

:no_subio_solo

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
rem  Misma espera con preguntas: un arranque en frio puede tardar.
set /a INTENTOS=0
:esperar_al_rescate
powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process | Where-Object {$_.Name -like 'python*' -and $_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; if($p){exit 0}else{exit 1}"
if not errorlevel 1 goto :rescate_ok
set /a INTENTOS+=1
if %INTENTOS% LSS 30 (
  ping -n 4 127.0.0.1 >nul
  goto :esperar_al_rescate
)
:rescate_ok
powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process | Where-Object {$_.Name -like 'python*' -and $_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; if($p){exit 0}else{exit 1}"
if errorlevel 1 (
  echo [%date% %time%] ALERTA: el motor sigue caido tras arrancarlo directo >> "%LOG%"
) else (
  echo [%date% %time%] motor levantado por la red de seguridad >> "%LOG%"
)

:fin
del "%CANDADO%" >nul 2>&1
exit /b 0

rem ---------------------------------------------------------------
rem  ¿Sigo esperando a que quede libre, o ya fue demasiado?
rem  Devuelve 1 = seguir esperando · 0 = aplicar igual.
rem  Una hora es el techo: una correccion urgente no puede quedarse
rem  fuera todo el dia porque siempre hay alguien conectado.
rem ---------------------------------------------------------------
rem ---------------------------------------------------------------
rem  ¿El candado es de una pasada viva o de una que murio?
rem  Devuelve 0 = caducado, se puede tomar · 1 = hay otra trabajando.
rem ---------------------------------------------------------------
:candado_caducado
set "EDAD=999"
for /f "usebackq delims=" %%E in (`powershell -NoProfile -Command "try{$t=(Get-Item '%CANDADO%').LastWriteTime; [int]((Get-Date)-$t).TotalMinutes}catch{999}"`) do set "EDAD=%%E"
if "%EDAD%"=="" set "EDAD=999"
if %EDAD% GEQ 30 (
  echo [%date% %time%] habia un candado de %EDAD% min sin soltar: se ignora >> "%LOG%"
  exit /b 0
)
exit /b 1

:aplazar_o_seguir
rem  Arranca en 0 a proposito: si PowerShell no contesta, la cuenta
rem  queda vacia y `if  GEQ 60` seria un error de sintaxis que deja
rem  el bot a medias sin decir nada.
set "MINUTOS=0"
for /f "usebackq delims=" %%M in (`powershell -NoProfile -Command "try{$t=(Get-Item '%ESPERA%').LastWriteTime; [int]((Get-Date)-$t).TotalMinutes}catch{0}"`) do set "MINUTOS=%%M"
if not defined MINUTOS set "MINUTOS=0"
if "%MINUTOS%"=="" set "MINUTOS=0"
if %MINUTOS% GEQ 60 (
  echo [%date% %time%] llevaba %MINUTOS% minutos esperando un hueco: se aplica igual >> "%LOG%"
  exit /b 0
)
echo [%date% %time%] hay gente trabajando: el cambio espera un hueco ^(%MINUTOS% min^) >> "%LOG%"
exit /b 1
