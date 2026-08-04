@echo off
rem ================================================================
rem  REVIVIR EXPRES el Motor de Glosas en este PC — SIN DOCKER
rem
rem  Igual que REVIVIR_EXPRESS_SIN_RESCATE.cmd pero sin necesitar
rem  Docker Desktop: el sistema corre directo con Python (que este
rem  PC ya usa para los otros bots) y el tunel con el programa
rem  oficial de Cloudflare. Base de datos NUEVA provisional; la
rem  historia se restaura cuando Google entregue el disco de la VM.
rem
rem  Necesita instalados: Python 3.11+ y Git. Y el TOKEN del tunel
rem  de Cloudflare (guia: docs/MIGRACION_PC_HOSPITAL.md, seccion
rem  "Arranque expres SIN rescate" — OJO: en este modo la URL del
rem  Public hostname es  localhost:8080  y no motor:8080).
rem
rem  Se puede ejecutar las veces que sea: no borra ni dana nada.
rem ================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Revivir expres Motor de Glosas — sin Docker
set "BASE=C:\motor-glosas"
set "REPO=%BASE%\repo"
set "REPO_URL=https://github.com/yesidbadillo820-ship-it/motor-glosas-hus.git"

echo ==============================================================
echo   REVIVIR EXPRES EL MOTOR DE GLOSAS — MODO SIN DOCKER
echo ==============================================================
echo.

rem ---------- 1) Verificar requisitos --------------------------------
echo [1/7] Verificando requisitos...
rem Las dependencias fijadas del sistema tienen paquete listo para
rem Python 3.11 a 3.13. Con 3.14+ Windows intentaria COMPILARLAS y
rem falla. Por eso se prefiere un 3.13/3.12/3.11 si esta instalado.
set "PYCMD="
py -3.13 --version >nul 2>&1 && set "PYCMD=py -3.13"
if not defined PYCMD py -3.12 --version >nul 2>&1 && set "PYCMD=py -3.12"
if not defined PYCMD py -3.11 --version >nul 2>&1 && set "PYCMD=py -3.11"
if not defined PYCMD py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
  echo.
  echo   FALTA PYTHON. Instalelo de: https://www.python.org/downloads/windows/
  echo   Baje el "Windows installer ^(64-bit^)" de la serie 3.13 y marque
  echo   la casilla "Add python.exe to PATH". Luego vuelva a dar doble clic.
  pause & exit /b 1
)
!PYCMD! --version > "%TEMP%\pyver_motor.txt" 2>&1
set /p PYVER=<"%TEMP%\pyver_motor.txt"
set "PYMAJ=" & set "PYMIN="
for /f "tokens=2,3 delims=. " %%a in ("!PYVER!") do (set "PYMAJ=%%a" & set "PYMIN=%%b")
if not "!PYMAJ!"=="3" (
  echo   No se pudo reconocer la version de Python ^(!PYVER!^). Pidale
  echo   ayuda al chat con este mensaje.
  pause & exit /b 1
)
if !PYMIN! GEQ 14 (
  echo.
  echo   Su Python es la version !PYMAJ!.!PYMIN! — demasiado NUEVA: varias
  echo   piezas del sistema aun no publican paquete para ella y Windows
  echo   intentaria compilarlas ^(falla^). La solucion es facil:
  echo   instale ADEMAS Python 3.13 ^(convive con el actual sin pelear^):
  echo     https://www.python.org/downloads/windows/
  echo   Baje el "Windows installer ^(64-bit^)" mas reciente de la serie
  echo   3.13, marque "Add python.exe to PATH", instale, y vuelva a
  echo   correr este instalador: el solo escogera el 3.13.
  pause & exit /b 1
)
if !PYMIN! LSS 11 (
  echo.
  echo   Su Python ^(!PYMAJ!.!PYMIN!^) es muy viejo. Instale la serie 3.13:
  echo   https://www.python.org/downloads/windows/ y vuelva a correr.
  pause & exit /b 1
)
git --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo   FALTA GIT. Instalelo de: https://git-scm.com/download/win
  echo   ^(todo con "Siguiente"; no necesita permisos de administrador^)
  echo   y vuelva a dar doble clic aqui.
  pause & exit /b 1
)
echo    Python y Git listos.

rem ---------- 2) Traer el repositorio --------------------------------
echo [2/7] Trayendo el codigo del repositorio...
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

rem ---------- 3) Crear las llaves del sistema (.env) -----------------
if exist "%REPO%\.env" (
  echo [3/7] Ya existe el archivo .env de una corrida anterior: se conserva.
  goto :entorno
)
echo [3/7] Creando las llaves del sistema...
echo.
set "PWADMIN="
set /p "PWADMIN=   Invente la contrasena del usuario admin ^(admin@hus.gov.co^): "
if "!PWADMIN!"=="" (
  echo   La contrasena no puede quedar vacia. Vuelva a correr el instalador.
  pause & exit /b 1
)
set "SK="
for /f %%a in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')"') do set "SK=%%a"
set "ALT="
for /f %%a in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N')"') do set "ALT=%%a"
if "!SK!"=="" (
  echo   No se pudo generar la llave interna. Reintente.
  pause & exit /b 1
)
echo.
echo   Llaves de la IA — opcionales, Enter para saltar y ponerlas luego.
echo   La de Groq es GRATIS y se saca en 2 min: https://console.groq.com/keys
set "GROQKEY="
set /p "GROQKEY=   GROQ_API_KEY  [Enter = saltar]: "
set "ANTKEY="
set /p "ANTKEY=   ANTHROPIC_API_KEY  [Enter = saltar]: "
set "GEMKEY="
set /p "GEMKEY=   GEMINI_API_KEY  [Enter = saltar]: "
(
  echo # Generado por REVIVIR_EXPRESS_SIN_DOCKER.cmd — no compartir.
  echo DATABASE_URL=sqlite:///C:/motor-glosas/repo/data/motorglosas.db
  echo SECRET_KEY=!SK!
  echo ADMIN_PASSWORD=!PWADMIN!
  echo AGENTE_LOTES_TOKEN=!ALT!
  echo GROQ_API_KEY=!GROQKEY!
  echo ANTHROPIC_API_KEY=!ANTKEY!
  echo GEMINI_API_KEY=!GEMKEY!
)>"%REPO%\.env"
echo    Archivo .env creado.

:entorno
rem ---------- 4) Preparar el entorno de Python -----------------------
echo [4/7] Preparando el entorno de Python ^(la primera vez tarda
echo        varios minutos: descarga las dependencias^)...
rem Si el entorno quedo de una corrida anterior con un Python 3.14+,
rem se rehace con el Python bueno.
if exist "%REPO%\venv\Scripts\python.exe" (
  "%REPO%\venv\Scripts\python.exe" --version > "%TEMP%\pyver_motor.txt" 2>&1
  set /p VENVVER=<"%TEMP%\pyver_motor.txt"
  set "VMIN="
  for /f "tokens=3 delims=. " %%a in ("!VENVVER!") do set "VMIN=%%a"
  if defined VMIN if !VMIN! GEQ 14 (
    echo    El entorno anterior quedo con Python !VENVVER:Python =!: se rehace.
    rmdir /s /q "%REPO%\venv"
  )
)
if not exist "%REPO%\venv\Scripts\python.exe" (
  !PYCMD! -m venv "%REPO%\venv"
  if errorlevel 1 (
    echo   ERROR creando el entorno de Python. Copie lo de arriba y
    echo   pidale ayuda al chat.
    pause & exit /b 1
  )
)
rem psycopg2 es solo para PostgreSQL; en este PC la base es SQLite y
rem ademas en Windows intentaria compilarse. Se salta.
findstr /v /i "psycopg2" "%REPO%\requirements.txt" > "%REPO%\data\requirements_local.txt"
"%REPO%\venv\Scripts\python.exe" -m pip install --upgrade pip -q
"%REPO%\venv\Scripts\python.exe" -m pip install -r "%REPO%\data\requirements_local.txt"
if errorlevel 1 (
  echo   ERROR instalando dependencias. Copie lo de arriba y pidale
  echo   ayuda al chat.
  pause & exit /b 1
)
echo    Entorno de Python listo.

rem ---------- 5) Tunel de Cloudflare ---------------------------------
echo [5/7] Configurando el tunel que publica la pagina...
if not exist "%BASE%\cloudflared.exe" (
  echo    Descargando cloudflared.exe ^(el programa del tunel^)...
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%BASE%\cloudflared.exe'"
  if not exist "%BASE%\cloudflared.exe" (
    echo   ERROR descargando cloudflared. ^¿Hay internet? Reintente.
    pause & exit /b 1
  )
)
findstr /b "TUNNEL_TOKEN=" "%REPO%\.env" >nul 2>&1
if not errorlevel 1 (
  echo    El token del tunel ya quedo guardado en una corrida anterior.
  goto :arranque
)
echo.
echo   Pegue aqui el TOKEN del tunel de Cloudflare. Sirve pegar el
echo   comando completo que muestra Cloudflare: de ahi se saca solo.
echo   RECUERDE: en el Public hostname de Cloudflare la URL para este
echo   modo es  localhost:8080
set "ENTRADA="
set /p "ENTRADA=   Token o comando: "
if "!ENTRADA!"=="" (
  echo   Sin token no se puede publicar la pagina. Siga la guia
  echo   docs/MIGRACION_PC_HOSPITAL.md — "Arranque expres" — y reintente.
  pause & exit /b 1
)
set "TOKEN="
for %%t in (!ENTRADA!) do set "TOKEN=%%t"
if not "!TOKEN:~0,3!"=="eyJ" (
  echo   Eso no parece un token: deberia ser una tira larga que empieza
  echo   por eyJ. Revise la guia y reintente.
  pause & exit /b 1
)
>>"%REPO%\.env" echo TUNNEL_TOKEN=!TOKEN!
echo    Token guardado.

:arranque
rem ---------- 6) Arranque automatico y tareas programadas ------------
echo [6/7] Dejando todo para que arranque solo...
(
  echo @echo off
  echo rem Arranca el servidor y el tunel del Motor de Glosas si no
  echo rem estan corriendo. Lo llama la carpeta Inicio de Windows y el
  echo rem autodeploy. Generado por REVIVIR_EXPRESS_SIN_DOCKER.cmd
  echo start "" /min cmd /c "%REPO%\tools\servidor_motor_local.cmd"
  echo start "" /min cmd /c "%REPO%\tools\tunel_motor_local.cmd"
)>"%BASE%\arrancar_motor_glosas.cmd"
copy /y "%BASE%\arrancar_motor_glosas.cmd" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MotorGlosas.cmd" >nul
if errorlevel 1 (
  echo   OJO: no se pudo dejar el arranque automatico en la carpeta
  echo   Inicio. Si el PC se reinicia, correr a mano:
  echo   %BASE%\arrancar_motor_glosas.cmd
) else (
  echo    Arranque automatico al iniciar sesion: listo.
)
schtasks /Create /F /TN "MotorGlosas_Autodeploy" /SC MINUTE /MO 5 ^
  /TR "\"%REPO%\tools\autodeploy_motor_local.cmd\"" >nul
if errorlevel 1 (
  echo   No se pudo crear la tarea de autodeploy ^(permisos^). El sistema
  echo   funciona igual; los cambios nuevos se aplican corriendo a mano
  echo   tools\autodeploy_motor_local.cmd
) else (
  echo    Autodeploy cada 5 minutos: listo.
)
if not exist "%REPO%\data\destino_backup.txt" (
  echo.
  echo   ^¿A que carpeta copiar la copia de seguridad diaria?
  echo   Ideal: el share del hospital o una carpeta de Drive/OneDrive.
  set "DESTINO="
  set /p "DESTINO=   Carpeta destino [Enter = C:\motor-glosas\copias]: "
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

rem ---------- 7) Encender ya -----------------------------------------
echo [7/7] Encendiendo el servidor y el tunel...
call "%BASE%\arrancar_motor_glosas.cmd"
echo.
echo ==============================================================
echo   LISTO. En 1-2 minutos:
echo    - En este PC:      http://localhost:8080
echo    - Desde internet:  https://iaglosassinac.help
echo.
echo   COMO ENTRA EL EQUIPO ^(base nueva provisional^):
echo    - Administrador: admin@hus.gov.co con la contrasena que
echo      acaba de inventar.
echo    - Cada auditor: su correo de siempre, y de contrasena la
echo      parte del correo antes del arroba ^(ej. glosashus04^).
echo      El sistema les pide cambiarla al entrar.
echo.
echo   Si la pagina no carga desde internet, revise que en Cloudflare
echo   el Public hostname tenga Type HTTP y URL  localhost:8080
echo.
echo   OJO: esta base arranca VACIA. La historia ^(oficios, envios,
echo   dictamenes^) vuelve cuando Google entregue el disco de la VM:
echo   ese dia avise al chat ANTES de restaurar nada.
echo.
echo   Este PC debe quedar SIEMPRE encendido y con la sesion iniciada
echo   ^(bloqueada esta bien^). En Energia: nunca suspender.
echo ==============================================================
pause
