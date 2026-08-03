@echo off
rem ================================================================
rem  AUTODEPLOY del Motor de Glosas en el PC del hospital.
rem  Lo ejecuta una tarea programada cada 5 minutos (la crea el
rem  instalador MONTAR_SERVIDOR_MOTOR_GLOSAS.cmd). Hace lo mismo que
rem  hacia la VM de Google: si hay codigo nuevo fusionado en la rama
rem  motor-glosas, lo baja y reconstruye los contenedores.
rem  No abre ventanas ni molesta: deja rastro en data\autodeploy.log
rem ================================================================
setlocal
set "REPO=C:\motor-glosas\repo"
if not exist "%REPO%\.git" exit /b 0
cd /d "%REPO%"

set "LOG=%REPO%\data\autodeploy.log"

git fetch origin motor-glosas >nul 2>&1
if errorlevel 1 (
  echo [%date% %time%] sin internet o sin acceso a GitHub: se reintenta en 5 min >> "%LOG%"
  exit /b 0
)

for /f %%a in ('git rev-parse HEAD') do set "LOCAL=%%a"
for /f %%a in ('git rev-parse origin/motor-glosas') do set "REMOTO=%%a"
if "%LOCAL%"=="%REMOTO%" exit /b 0

echo [%date% %time%] codigo nuevo detectado: %REMOTO:~0,7% — aplicando... >> "%LOG%"
git reset --hard origin/motor-glosas >> "%LOG%" 2>&1
docker compose up -d --build >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR al reconstruir: revisar arriba >> "%LOG%"
) else (
  echo [%date% %time%] deploy aplicado correctamente >> "%LOG%"
)
exit /b 0
