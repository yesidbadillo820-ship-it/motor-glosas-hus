@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo    Instalador del BOT de glosas HUS
echo ============================================
echo.

rem --- 0. Detectar ejecucion desde DENTRO del ZIP sin extraer ---
if not exist "%~dp0organizar_correos_glosas.py" (
  echo [X] No encuentro los archivos del bot junto a este instalador.
  echo.
  echo     Estas ejecutando desde DENTRO del archivo ZIP sin extraerlo.
  echo     Windows solo saca el instalador a una carpeta temporal y deja
  echo     el resto adentro, por eso falla.
  echo.
  echo     COMO HACERLO BIEN:
  echo       1. Clic derecho al ZIP descargado - "Extraer todo..."
  echo       2. Elige una carpeta fija, ej: C:\bot-glosas
  echo       3. Entra a la carpeta extraida - tools
  echo       4. Ejecuta este instalador desde alli
  pause
  exit /b 1
)

echo El bot lee la bandeja de correo, clasifica cada mensaje en
echo INICIAL / RATIFICADA / DEVOLUCIONES / CONCILIACIONES, detecta
echo la entidad y archiva todo en el servidor de glosas.
echo.

rem --- 1. Python ---
py --version >nul 2>&1
if errorlevel 1 (
  echo [X] Python no esta instalado.
  echo     Descargalo de https://www.python.org/downloads/
  echo     y durante la instalacion marca "Add python.exe to PATH".
  pause
  exit /b 1
)
for /f "tokens=*" %%v in ('py --version') do echo [OK] %%v

rem --- 2. Dependencias ---
echo Instalando dependencias, espera un momento...
py -m pip install --quiet --disable-pip-version-check reportlab openpyxl pdfplumber
if errorlevel 1 (
  echo [X] Fallo la instalacion de dependencias. Revisa la conexion a internet.
  pause
  exit /b 1
)
echo [OK] Dependencias instaladas.
echo.

rem --- 3. Credenciales ---
set "CORREO=%GLOSAS_IMAP_USER%"
if "!CORREO!"=="" (
  set /p CORREO="Correo de la bandeja [glosasydevoluciones@hus.gov.co]: "
  if "!CORREO!"=="" set "CORREO=glosasydevoluciones@hus.gov.co"
  setx GLOSAS_IMAP_USER "!CORREO!" >nul
)
echo [OK] Correo: !CORREO!

set "CLAVE=%GLOSAS_IMAP_PASSWORD%"
if not "!CLAVE!"=="" (
  set /p CAMBIAR="Ya hay una contrasena guardada. Reemplazarla por una nueva? (S/N): "
  if /i "!CAMBIAR!"=="S" set "CLAVE="
)
if "!CLAVE!"=="" (
  echo.
  echo Necesitas una CONTRASENA DE APLICACION de Google, no la clave normal:
  echo   1. Entra a la cuenta de correo en el navegador
  echo   2. Abre https://myaccount.google.com/apppasswords
  echo      Requiere verificacion en dos pasos activa
  echo   3. Crea una con nombre "Bot Glosas" y copia las 16 letras
  echo.
  set /p CLAVE="Pega aqui la contrasena de aplicacion, sin espacios: "
  set "CLAVE=!CLAVE: =!"
  setx GLOSAS_IMAP_PASSWORD "!CLAVE!" >nul
)
echo [OK] Credenciales guardadas en este equipo.
echo.

rem --- 4. Prueba en simulacro: no archiva ni marca nada ---
echo Probando conexion y clasificacion con los ultimos correos...
echo ------------------------------------------------------------
set "GLOSAS_IMAP_USER=!CORREO!"
set "GLOSAS_IMAP_PASSWORD=!CLAVE!"
py organizar_correos_glosas.py --dry-run --max 10
if errorlevel 1 (
  echo.
  echo [X] La prueba fallo. Lee el mensaje de arriba:
  echo     - "login IMAP rechazado" = la contrasena no es de aplicacion
  echo     - Reintenta ejecutando de nuevo este instalador
  pause
  exit /b 1
)
echo ------------------------------------------------------------
echo [OK] El bot se conecto y clasifico correctamente. Simulacro: nada se movio.
echo.

rem --- 5. Programar cada 15 minutos ---
set /p PROGRAMAR="Programar el bot para que corra solo cada 15 minutos? (S/N): "
if /i "!PROGRAMAR!"=="S" call instalar_organizador_correos.bat
echo.
echo LISTO. Para una corrida manual: doble clic a organizar_correos_glosas.bat
echo El registro de lo archivado queda en:
echo   Z:\...\03-GLOSAS ESCANEADAS 2.0\00-CONTROL AUTOMATICO\registro_AAAA-MM.csv
pause
