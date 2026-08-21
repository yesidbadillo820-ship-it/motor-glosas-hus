@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title Motor de Glosas - dejar que arranque solo
rem ================================================================
rem  DEJAR EL MOTOR ARRANCANDO SOLO AL PRENDER EL PC.
rem
rem  POR QUE EXISTE (21-08-2026). El arranque estaba en la carpeta
rem  Inicio de Windows, que se dispara al INICIAR SESION. O sea: si
rem  el PC se reinicia de noche y nadie entra, el hospital amanece
rem  sin portal. Paso el 21-08 a las 8:57 de la manana y hubo que
rem  sacarlo a mano.
rem
rem  Esto crea una tarea de Windows que arranca al PRENDER el equipo,
rem  sin que nadie tenga que iniciar sesion.
rem
rem  POR QUE PIDE LA CONTRASENA. La tarea corre con la cuenta del
rem  usuario a proposito: el motor necesita entrar a la carpeta del
rem  servidor (\\Prime\radicacion_2026) para encontrar los soportes,
rem  y la cuenta del sistema normalmente no tiene ese permiso. La
rem  contrasena la pide Windows, se guarda en la boveda de Windows y
rem  NO queda escrita en ningun archivo de este repositorio.
rem
rem  Es seguro correrlo varias veces: si la tarea ya existe, se
rem  reemplaza.
rem ================================================================

set "BASE=C:\motor-glosas"
set "REPO=%BASE%\repo"
set "TAREA=MotorGlosas_Arranque"
set "LANZADOR=%BASE%\arrancar_motor_glosas.cmd"

echo.
echo   ============================================================
echo     MOTOR DE GLOSAS - que arranque solo al prender el PC
echo   ============================================================
echo.

rem ---------- 1) Comprobar que este todo en su sitio -------------
if not exist "%REPO%\.git" (
  echo   NO se encontro el motor en %REPO%
  echo   Este instalador es para el PC de cartera del HUS.
  echo.
  pause
  exit /b 1
)
if not exist "%LANZADOR%" (
  echo   Falta %LANZADOR%
  echo   Corra primero tools\REVIVIR_EXPRESS_SIN_DOCKER.cmd
  echo.
  pause
  exit /b 1
)

rem ---------- 2) Quien es el usuario -----------------------------
set "CUENTA=%USERDOMAIN%\%USERNAME%"
echo   La tarea va a correr con la cuenta:  %CUENTA%
echo.
echo   Windows le va a pedir la contrasena de ESA cuenta.
echo   La escribe usted; no se guarda en ningun archivo del motor.
echo.
pause
echo.

rem ---------- 3) Crear la tarea ---------------------------------
echo   Creando la tarea de arranque...
rem  /DELAY 0001:00 = esperar un minuto despues de prender el PC.
rem  Al arrancar, la red del hospital todavia no esta lista y el
rem  motor necesita llegar a \\Prime\radicacion_2026 para el indice
rem  de soportes. Un minuto le da tiempo a la red.
rem
rem  SIN /RL HIGHEST a proposito: el motor no necesita permisos de
rem  administrador (escucha en 127.0.0.1 y lee una carpeta de red
rem  con la cuenta del usuario). Pedir permisos que no hacen falta
rem  solo agrega formas de que falle.
schtasks /Create /F /TN "%TAREA%" /SC ONSTART /DELAY 0001:00 ^
  /RU "%CUENTA%" /RP * /TR "\"%LANZADOR%\""
if errorlevel 1 (
  echo.
  echo   NO se pudo crear la tarea.
  echo.
  echo   Las dos causas mas comunes:
  echo     1. La contrasena no era la correcta. Vuelva a intentar.
  echo     2. Hace falta abrir esta ventana como administrador:
  echo        clic derecho sobre el archivo - Ejecutar como administrador.
  echo.
  echo   Mientras tanto el motor sigue arrancando al iniciar sesion,
  echo   como hasta ahora. No se rompio nada.
  echo.
  pause
  exit /b 1
)

rem ---------- 4) Comprobar que quedo ----------------------------
echo.
echo   Comprobando...
schtasks /Query /TN "%TAREA%" >nul 2>&1
if errorlevel 1 (
  echo   La tarea no aparece. Algo fallo; avise.
  echo.
  pause
  exit /b 1
)

echo.
echo   ============================================================
echo     LISTO. El motor va a arrancar solo al prender el PC,
echo     sin que nadie tenga que iniciar sesion.
echo   ============================================================
echo.
echo   Lo que NO cambio:
echo     - Sigue arrancando tambien al iniciar sesion (respaldo).
echo     - El vigilante sigue reviviendo el motor si se cae.
echo     - El autodespliegue sigue bajando el codigo nuevo cada 5 min.
echo.
echo   OJO con los soportes: tras prender el PC, el indice tarda
echo   unos minutos en recorrer el servidor. Si busca una factura
echo   y no aparece, mire en Diagnostico que no diga 'Indexando'.
echo.
echo   COMO COMPROBARLO DE VERDAD: reinicie el PC y, SIN iniciar
echo   sesion, abra el portal desde otro equipo o desde el celular.
echo   Si carga, quedo bien.
echo.
echo   Si algun dia cambia su contrasena de Windows, vuelva a correr
echo   este archivo: la tarea guarda la contrasena vieja y dejaria de
echo   arrancar en silencio.
echo.
pause
endlocal
