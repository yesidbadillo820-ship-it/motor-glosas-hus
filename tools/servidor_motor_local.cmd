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

rem Si ya hay un servidor corriendo, no duplicar
powershell -NoProfile -Command "$p=Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object {$_.CommandLine -match 'uvicorn app.main:app'}; if($p){exit 1}else{exit 0}"
if errorlevel 1 exit /b 0

cd /d "%REPO%"
rem Cargar TODO el .env como variables de entorno de verdad. En Docker
rem las inyectaba docker compose; aca muchas partes del codigo las leen
rem con os.getenv (llaves de IA, toggles) y no basta con que Settings
rem lea el archivo. Se saltan las lineas de comentario (#).
if exist "%REPO%\.env" (
  for /f "usebackq eol=# tokens=1* delims==" %%a in ("%REPO%\.env") do set "%%a=%%b"
)
set "SOPORTES_ROOT=%REPO%\data\soportes"
set "SOPORTES_LOCAL_ROOT=%REPO%\data\soportes"
if not exist "%REPO%\data\soportes" mkdir "%REPO%\data\soportes"
set "LOG=%REPO%\data\servidor.log"

:loop
rem Si el registro pasa de ~5 MB, se reinicia para no llenar el disco
for %%s in ("%LOG%") do if %%~zs GTR 5000000 del "%LOG%" >nul 2>&1
echo [%date% %time%] arrancando el servidor... >> "%LOG%"
"%REPO%\venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8080 >> "%LOG%" 2>&1
echo [%date% %time%] el servidor se detuvo; se reinicia en 5 segundos >> "%LOG%"
timeout /t 5 /nobreak >nul
goto :loop
