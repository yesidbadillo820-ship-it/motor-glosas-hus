@echo off
rem ================================================================
rem  SERVIDOR del Motor de Glosas en modo SIN DOCKER (Python directo).
rem  Lo arranca C:\motor-glosas\arrancar_motor_glosas.cmd (y este a su
rem  vez la carpeta Inicio de Windows al iniciar sesion). Mantiene el
rem  servidor vivo: si se cae, lo levanta solo a los 5 segundos.
rem  Registro en data\servidor.log
rem ================================================================
setlocal
title MotorGlosasServidor
set "REPO=C:\motor-glosas\repo"
if not exist "%REPO%\venv\Scripts\python.exe" exit /b 1

rem ---------------------------------------------------------------
rem  UN SOLO VIGILANTE (21-08-2026).
rem
rem  El autodeploy corre cada 5 minutos y SIEMPRE llama a
rem  arrancar_motor_glosas.cmd, que abre este vigilante sin preguntar
rem  si ya hay uno. Cada pasada abria otra ventana: el PC de cartera
rem  amanecio con CUATRO ventanas "MotorGlosasServidor" y cuatro
rem  motores, dos de ellos en el puerto 8000.
rem
rem  Eso no es solo desorden. Cada motor leyo las claves y el codigo
rem  cuando arranco, asi que pueden estar mirando bases de datos
rem  distintas. El 20-08 eso le escondio a la auditora su consolidado
rem  entero -1.189 facturas- y costo una tarde entera entender por que.
rem
rem  Se cuenta cuantos procesos corren este mismo archivo. Si hay mas
rem  de uno, el que sobra se va en silencio. Mismo metodo que ya usa
rem  el bucle de abajo para no arrancar dos motores.
rem ---------------------------------------------------------------
powershell -NoProfile -Command "$n=@(Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'servidor_motor_local'}).Count; if($n -gt 1){exit 1}else{exit 0}"
if errorlevel 1 (
  echo [%date% %time%] ya habia un vigilante corriendo: este sobra y se cierra >> "%REPO%\data\servidor.log"
  exit /b 0
)

cd /d "%REPO%"
rem Carpeta donde el motor busca los soportes.
rem
rem Por defecto usa la carpeta local del repo (a donde suben los ZIP desde
rem la pantalla). Si el PC tiene acceso al servidor de archivos del HUS, se
rem escribe la ruta en config\soportes_root.txt (una sola linea, por ejemplo
rem \\Prime\radicacion_2026) y el motor indexa el servidor directo.
rem Ese archivo NO va al repositorio: asi el autodeploy no lo borra.
rem 18-08-2026.
set "SOPORTES_ROOT=%REPO%\data\soportes"
if exist "%REPO%\config\soportes_root.txt" (
  for /f "usebackq delims=" %%R in ("%REPO%\config\soportes_root.txt") do (
    if not "%%R"=="" set "SOPORTES_ROOT=%%R"
  )
)
set "SOPORTES_LOCAL_ROOT=%REPO%\data\soportes"
if not exist "%REPO%\data\soportes" mkdir "%REPO%\data\soportes"
set "LOG=%REPO%\data\servidor.log"

:loop
rem ¿Ya hay un servidor de PRODUCCION arriba? Entonces este vigilante
rem espera, NO arranca otro encima.
rem
rem Dos correcciones del 04-08-2026 en una sola linea:
rem  1. El filtro mira el PUERTO. Antes bastaba con que existiera
rem     cualquier uvicorn de la aplicacion, asi que mientras el auditor
rem     tuviera abierto su motor de pruebas (8000), este vigilante se
rem     negaba a arrancar — y si la pagina por internet se caia, NO
rem     volvia sola.
rem  2. La comprobacion va DENTRO del bucle. Estaba antes, una sola vez:
rem     si quedaban dos ventanas de vigilancia abiertas (pasa facil: el
rem     autodeploy vuelve a llamar al arrancador cada 5 minutos), la
rem     segunda entraba al bucle igual y se pasaba el dia levantando un
rem     servidor que moria al instante contra el puerto ocupado, un
rem     proceso nuevo cada 5 segundos llenando el registro. Asi, el
rem     vigilante de mas simplemente espera: si el otro se cae, este
rem     toma el relevo.
powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; if($p){exit 1}else{exit 0}"
if errorlevel 1 (
  timeout /t 5 /nobreak >nul
  goto :loop
)

rem Cargar TODO el .env como variables de entorno de verdad. En Docker
rem las inyectaba docker compose; aca muchas partes del codigo las leen
rem con os.getenv (llaves de IA, toggles) y no basta con que Settings
rem lea el archivo. Se saltan las lineas de comentario (#).
rem
rem OJO — esto va DENTRO del bucle desde el 04-08-2026. Estaba antes, y
rem por eso el motor de la pagina publica se quedaba con las claves del
rem dia en que se abrio esta ventana: cuando el servidor se caia, el
rem vigilante lo revivia heredando el ambiente VIEJO, y las variables de
rem entorno le ganan al archivo. El auditor cambio la clave de Groq,
rem reinicio todo lo que pudo, y la pagina por internet siguio horas
rem respondiendo «su clave esta invalida» con la clave anterior
rem (gsk_5CxaRq) mientras el archivo ya tenia la nueva. Releer aca hace
rem que cada reinicio tome las claves de HOY.
if exist "%REPO%\.env" (
  for /f "usebackq eol=# tokens=1* delims==" %%a in ("%REPO%\.env") do set "%%a=%%b"
)
rem Si el registro pasa de ~5 MB, se reinicia para no llenar el disco
for %%s in ("%LOG%") do if %%~zs GTR 5000000 del "%LOG%" >nul 2>&1
echo [%date% %time%] arrancando el servidor... >> "%LOG%"
"%REPO%\venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8080 >> "%LOG%" 2>&1
echo [%date% %time%] el servidor se detuvo; se reinicia en 5 segundos >> "%LOG%"
timeout /t 5 /nobreak >nul
goto :loop
