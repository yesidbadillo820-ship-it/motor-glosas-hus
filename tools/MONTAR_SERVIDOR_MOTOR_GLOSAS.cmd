@echo off
rem ================================================================
rem  MONTAR EL SERVIDOR DEL MOTOR DE GLOSAS EN ESTE PC (doble clic)
rem
rem  Migra el sistema desde Google Cloud a este computador del
rem  hospital: misma pagina (iaglosassinac.help), mismos datos,
rem  mismo deploy automatico. Guia completa:
rem  docs/MIGRACION_PC_HOSPITAL.md
rem
rem  Necesita, YA instalados en el PC (una sola vez):
rem   - Docker Desktop (www.docker.com/products/docker-desktop)
rem   - Git (git-scm.com/download/win)
rem  Y el paquete de rescate de la VM: rescate-motor-glosas.tgz
rem  (fase 1 de la guia; normalmente queda en Descargas).
rem
rem  Se puede ejecutar las veces que sea: no borra ni dana nada.
rem ================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Montar servidor Motor de Glosas
set "BASE=C:\motor-glosas"
set "REPO=%BASE%\repo"
set "REPO_URL=https://github.com/yesidbadillo820-ship-it/motor-glosas-hus.git"

echo ==============================================================
echo   MONTAR EL SERVIDOR DEL MOTOR DE GLOSAS EN ESTE PC
echo ==============================================================
echo.

rem ---------- 1) Verificar requisitos --------------------------------
echo [1/6] Verificando requisitos...
git --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo   FALTA GIT. Instalelo de: https://git-scm.com/download/win
  echo   ^(todo con "Siguiente"^) y vuelva a dar doble clic aqui.
  pause & exit /b 1
)
docker --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo   FALTA DOCKER DESKTOP. Instalelo de:
  echo   https://www.docker.com/products/docker-desktop/
  echo   ^(acepte WSL 2 si lo pregunta; puede pedir reiniciar^).
  echo   Luego abralo, espere la ballena verde, y vuelva aca.
  pause & exit /b 1
)
docker info >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Docker Desktop esta instalado pero NO esta corriendo.
  echo   Abralo desde el menu Inicio, espere la ballena verde de la
  echo   bandeja, y vuelva a dar doble clic aqui.
  pause & exit /b 1
)
echo    Git y Docker listos.

rem ---------- 2) Traer el repositorio --------------------------------
echo [2/6] Trayendo el codigo del repositorio...
if not exist "%BASE%" mkdir "%BASE%"
if exist "%REPO%\.git" (
  cd /d "%REPO%"
  git fetch origin motor-glosas
  git checkout motor-glosas >nul 2>&1
  git reset --hard origin/motor-glosas
) else (
  git clone -b motor-glosas "%REPO_URL%" "%REPO%"
  if errorlevel 1 (
    echo   ERROR clonando el repositorio. ^¿Hay internet? Reintente.
    pause & exit /b 1
  )
)
cd /d "%REPO%"
if not exist "%REPO%\data" mkdir "%REPO%\data"

rem ---------- 3) Restaurar el rescate de la VM -----------------------
echo [3/6] Restaurando los datos rescatados de la VM...
set "YATIENE=0"
if exist "%REPO%\.env" if exist "%REPO%\deploy\cloudflared\config.yml" if exist "%REPO%\data\motorglosas.db" set "YATIENE=1"
if "%YATIENE%"=="1" (
  echo    Ya hay datos restaurados de una corrida anterior: se conservan.
  goto :levantar
)

set "PAQUETE=%USERPROFILE%\Downloads\rescate-motor-glosas.tgz"
if not exist "%PAQUETE%" (
  echo.
  set /p "PAQUETE=   Ruta del archivo rescate-motor-glosas.tgz: "
)
if not exist "!PAQUETE!" (
  echo   NO se encontro el paquete de rescate. Sin el, el sistema
  echo   arrancaria VACIO ^(sin la base ni la llave del tunel^).
  echo   Descarguelo siguiendo la fase 1 de docs/MIGRACION_PC_HOSPITAL.md
  echo   y vuelva a dar doble clic aqui.
  pause & exit /b 1
)

set "TMPDIR=%TEMP%\rescate_motor_%RANDOM%"
mkdir "%TMPDIR%"
tar -xzf "!PAQUETE!" -C "%TMPDIR%"
if errorlevel 1 (
  echo   ERROR abriendo el paquete. ^¿Se descargo completo?
  pause & exit /b 1
)

rem .env (llaves del sistema) y deploy/cloudflared (llave del tunel)
if exist "%TMPDIR%\.env" copy /y "%TMPDIR%\.env" "%REPO%\.env" >nul
if exist "%TMPDIR%\deploy\cloudflared" xcopy /e /y /i "%TMPDIR%\deploy\cloudflared" "%REPO%\deploy\cloudflared" >nul

rem La copia de la base (el .db mas reciente del paquete) pasa a ser la base viva
set "DBRESC="
for /r "%TMPDIR%" %%f in (*.db) do set "DBRESC=%%f"
if defined DBRESC (
  copy /y "!DBRESC!" "%REPO%\data\motorglosas.db" >nul
  echo    Base de datos restaurada: !DBRESC!
) else (
  echo   OJO: el paquete no traia ninguna base .db — revise la fase 1.
  pause & exit /b 1
)
if not exist "%REPO%\.env" (
  echo   OJO: el paquete no traia el archivo .env — revise la fase 1.
  pause & exit /b 1
)
if not exist "%REPO%\deploy\cloudflared\config.yml" (
  echo   OJO: el paquete no traia la llave del tunel — revise la fase 1.
  pause & exit /b 1
)
rmdir /s /q "%TMPDIR%" >nul 2>&1

:levantar
rem ---------- 4) Construir y levantar --------------------------------
echo [4/6] Construyendo y levantando el sistema ^(la primera vez tarda
echo        varios minutos: descarga y compila todo^)...
docker compose up -d --build
if errorlevel 1 (
  echo   ERROR levantando los contenedores. Copie lo de arriba y pidale
  echo   ayuda al chat.
  pause & exit /b 1
)

rem ---------- 5) Tareas programadas ----------------------------------
echo [5/6] Programando el deploy automatico y la copia de seguridad...
schtasks /Create /F /TN "MotorGlosas_Autodeploy" /SC MINUTE /MO 5 ^
  /TR "\"%REPO%\tools\autodeploy_motor_glosas.cmd\"" >nul
if errorlevel 1 (
  echo   No se pudo crear la tarea de autodeploy ^(permisos^). El sistema
  echo   funciona igual, pero los cambios nuevos habra que aplicarlos a
  echo   mano corriendo tools\autodeploy_motor_glosas.cmd
) else (
  echo    Autodeploy cada 5 minutos: listo.
)

if not exist "%REPO%\data\destino_backup.txt" (
  echo.
  echo   ^¿A que carpeta copiar la copia de seguridad diaria?
  echo   Ideal: el share del hospital o una carpeta de Drive/OneDrive.
  set /p "DESTINO=   Carpeta destino (Enter = C:\motor-glosas\copias): "
  if "!DESTINO!"=="" set "DESTINO=C:\motor-glosas\copias"
  >"%REPO%\data\destino_backup.txt" echo !DESTINO!
)
schtasks /Create /F /TN "MotorGlosas_Backup" /SC DAILY /ST 09:00 ^
  /TR "\"%REPO%\tools\copiar_backup_motor_glosas.cmd\"" >nul
if errorlevel 1 (
  echo   No se pudo crear la tarea de backup; correr a mano
  echo   tools\copiar_backup_motor_glosas.cmd cuando se quiera.
) else (
  echo    Copia de seguridad diaria 9:00 a.m.: lista.
)

rem ---------- 6) Estado final ----------------------------------------
echo [6/6] Estado de los contenedores:
docker compose ps
echo.
echo ==============================================================
echo   LISTO. En 1-2 minutos abra:  https://iaglosassinac.help
echo   Debe cargar la pagina con todos los datos de siempre.
echo.
echo   Recuerde: este PC debe quedar ENCENDIDO y con la sesion
echo   iniciada ^(bloqueada esta bien^). Docker Desktop debe tener
echo   activado "Start Docker Desktop when you sign in".
echo.
echo   Cuando verifique que todo funciona, apague la VM de Google
echo   ^(fase 4 de docs/MIGRACION_PC_HOSPITAL.md^).
echo ==============================================================
pause
