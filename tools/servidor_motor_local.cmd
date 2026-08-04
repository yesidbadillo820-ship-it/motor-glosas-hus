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

rem Si ya hay un servidor de PRODUCCION corriendo, no duplicar.
rem El filtro mira el puerto desde el 04-08-2026: antes bastaba con que
rem existiera cualquier uvicorn de la aplicacion, asi que mientras el
rem auditor tuviera abierto su motor de pruebas (puerto 8000) este
rem vigilante se negaba a arrancar — y si la pagina por internet se caia,
rem NO volvia sola.
powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object {$_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; if($p){exit 1}else{exit 0}"
if errorlevel 1 exit /b 0

cd /d "%REPO%"
set "SOPORTES_ROOT=%REPO%\data\soportes"
set "SOPORTES_LOCAL_ROOT=%REPO%\data\soportes"
if not exist "%REPO%\data\soportes" mkdir "%REPO%\data\soportes"
set "LOG=%REPO%\data\servidor.log"

:loop
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
