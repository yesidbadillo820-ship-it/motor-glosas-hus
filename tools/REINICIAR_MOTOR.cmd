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

REM --- 1. Cerrar lo que este escuchando el puerto ---------------------
echo  [1/3] Buscando motores encendidos...
set "HUBO=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:"LISTENING" ^| findstr /C:":%PUERTO% "') do (
  if not "%%P"=="0" (
    echo        - cerrando proceso %%P
    taskkill /PID %%P /T /F >nul 2>&1
    set "HUBO=1"
  )
)
if "%HUBO%"=="0" (
  echo        No habia ningun motor encendido. Bien.
) else (
  echo        Motores anteriores cerrados.
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

REM --- 3. Arrancar uno solo -------------------------------------------
echo  [3/3] Arrancando el motor...
echo.
echo  ------------------------------------------------------------
echo   Al arrancar fijate en estas dos lineas del log:
echo     [IA-PROVIDERS] ... groq=OK gsk_xxxxxx...
echo     [MOTOR] Un solo motor atendiendo - PID ...
echo   Si en vez de [MOTOR] aparece [MOTOR-DUPLICADO], quedo otro
echo   motor vivo: cierra esta ventana y vuelve a dar doble clic.
echo  ------------------------------------------------------------
echo.
echo   Para apagarlo: Ctrl + C  (o cierra esta ventana).
echo   Direccion: http://127.0.0.1:%PUERTO%
echo.

where uvicorn >nul 2>&1
if %ERRORLEVEL%==0 (
  uvicorn app.main:app --port %PUERTO%
) else (
  py -m uvicorn app.main:app --port %PUERTO%
)

echo.
echo  El motor se detuvo.
pause
