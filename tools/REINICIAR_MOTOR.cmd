@echo off
REM ====================================================================
REM  REINICIAR_MOTOR.cmd  -  Apaga TODO y prende un solo motor limpio.
REM
REM  Por que existe (04-08-2026): al cambiar la clave de la IA en el
REM  archivo .env el auditor reiniciaba abriendo otra ventana, pero el
REM  motor anterior seguia vivo. En Windows los dos se quedan con el
REM  mismo puerto 8000 y las peticiones caen en cualquiera de los dos:
REM  el viejo responde con la CLAVE VIEJA y el CODIGO VIEJO. Resultado:
REM  el arranque decia "clave OK" y el analisis fallaba con "clave
REM  invalida", sin que nada en pantalla lo explicara.
REM
REM  Este bot cierra todos los motores que esten escuchando el puerto y
REM  deja UNO solo, recien arrancado, con lo que dice el .env de hoy.
REM
REM  USO: doble clic. Dejar esta ventana abierta mientras se trabaja.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions
title MOTOR GLOSAS HUS - Reiniciar motor

cd /d "%~dp0.."

set "PUERTO=%MOTOR_GLOSAS_PUERTO%"
if "%PUERTO%"=="" set "PUERTO=8000"

echo.
echo  ============================================================
echo    REINICIAR EL MOTOR DE GLOSAS  (puerto %PUERTO%)
echo  ============================================================
echo.
echo  Carpeta del proyecto: %CD%
echo.

REM --- 1. Dejar libre el puerto, sin daños ----------------------------
REM Todo el trabajo delicado vive en tools\reiniciar_motor.ps1 (ahi esta
REM explicado por que cada cosa se hace asi). Si devuelve error, NO se
REM arranca nada: quedo algo vivo que hay que mirar primero.
echo  [1/3] Buscando motores encendidos...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0reiniciar_motor.ps1" -Puerto %PUERTO%
if errorlevel 1 (
  echo.
  echo   No arranco el motor: lea el aviso de arriba.
  echo.
  pause
  exit /b 1
)

REM --- 2. Aviso si el .env no esta donde debe -------------------------
echo  [2/3] Revisando la configuracion...
if not exist "%CD%\.env" (
  echo.
  echo        [!] No encuentro el archivo .env en %CD%
  echo            Sin el, el motor arranca SIN claves de IA y ningun
  echo            analisis va a funcionar.
  echo.
  pause
)

REM Cargar el .env como variables de entorno de verdad, igual que hace
REM tools\servidor_motor_local.cmd: varias partes del codigo leen las
REM llaves con os.getenv y asi los dos motores arrancan iguales.
if exist "%CD%\.env" (
  for /f "usebackq eol=# tokens=1* delims==" %%a in ("%CD%\.env") do set "%%a=%%b"
)

REM --- 3. Arrancar uno solo -------------------------------------------
echo  [3/3] Arrancando el motor...
echo.
echo  ------------------------------------------------------------
echo   Al arrancar fijate en estas lineas del log:
echo     [IA-PROVIDERS] ... groq=OK gsk_xxxxxx...
echo     [MOTOR] Un solo motor atendiendo - PID ... - puerto %PUERTO%
echo.
echo   Si aparece [MOTOR-DUPLICADO] hay DOS en el mismo puerto: eso si
echo   es un problema, anota los PID y avisa.
echo   Si aparece [MOTORES] con puertos distintos, es NORMAL en este
echo   equipo: el del 8080 es la pagina por internet. No lo cierres.
echo  ------------------------------------------------------------
echo.
echo   Para apagarlo: Ctrl + C  (o cierra esta ventana).
echo   Direccion: http://127.0.0.1:%PUERTO%
echo.

REM El interprete del propio proyecto: el uvicorn del PATH puede ser otro
REM (otra instalacion de Python, sin las librerias de este repo).
if exist "%CD%\venv\Scripts\python.exe" (
  "%CD%\venv\Scripts\python.exe" -m uvicorn app.main:app --port %PUERTO%
) else (
  where uvicorn >nul 2>&1
  if %ERRORLEVEL%==0 (
    uvicorn app.main:app --port %PUERTO%
  ) else (
    py -m uvicorn app.main:app --port %PUERTO%
  )
)

echo.
echo  El motor se detuvo.
pause
