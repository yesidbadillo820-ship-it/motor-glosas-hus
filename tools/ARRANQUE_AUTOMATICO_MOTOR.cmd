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

rem ---------- 1b) ¿Hay permisos de administrador? ---------------
rem  SE COMPRUEBA ANTES DE TOCAR NADA (21-08-2026, noche).
rem
rem  Crear la tarea usa /F, que primero borra la que hubiera. Si
rem  despues falla por falta de permisos, se queda SIN NINGUNA: el
rem  intento deja el PC peor de como estaba. Paso de verdad: por la
rem  manana la tarea quedo creada, por la tarde un intento sin
rem  permisos contesto 'Acceso denegado', y en la noche ya no habia
rem  tarea de arranque. Nadie se entera hasta el proximo reinicio.
rem
rem  'net session' solo funciona con permisos de administrador: es la
rem  forma clasica de preguntarlo en un .cmd.
net session >nul 2>&1
if errorlevel 1 (
  echo   Esta ventana NO tiene permisos de administrador, y sin ellos
  echo   Windows no deja crear una tarea que guarde una contrasena.
  echo.
  echo   QUE HACER: cierre esta ventana. Busque el archivo
  echo     %%~f0
  echo   haga clic DERECHO encima y elija 'Ejecutar como administrador'.
  echo.
  echo   OJO: si al hacerlo Windows le pide OTRA cuenta, mas adelante
  echo   este archivo le va a preguntar con que cuenta debe correr la
  echo   tarea. Ahi escriba la cuenta del motor, NO la de administrador.
  echo.
  echo   No se toco nada: todo quedo como estaba.
  echo.
  pause
  exit /b 1
)

rem ---------- 2) Quien es el usuario -----------------------------
rem  LA TRAMPA DE 'EJECUTAR COMO ADMINISTRADOR' (21-08-2026, tarde).
rem  Crear una tarea que corre con una cuenta y su contrasena guardada
rem  exige permisos de administrador: sin ellos schtasks contesta
rem  'Acceso denegado'. Pero al abrir la ventana como administrador, si
rem  Windows pide OTRA cuenta, la ventana pasa a correr con ESA otra y
rem  %USERNAME% ya no es la del auditor.
rem
rem  Asi fue como la tarea de la manana quedo puesta con la cuenta
rem  cpimiento cuando la del motor es cartera. No da error: la tarea
rem  queda, el motor arranca, y si esa cuenta no entra a la carpeta de
rem  soportes del servidor, el indice amanece vacio sin que nadie
rem  entienda por que. Por eso ahora se pregunta, en vez de suponer.
set "CUENTA=%USERDOMAIN%\%USERNAME%"
echo   Esta ventana esta corriendo con la cuenta:  %CUENTA%
echo.
echo   OJO: la tarea tiene que correr con la cuenta que usa el motor
echo   todos los dias, la que SI entra a la carpeta de soportes del
echo   servidor. Si abrio esta ventana como administrador y Windows le
echo   pidio otra cuenta, arriba aparece esa otra y NO es la que sirve.
echo.
set "OTRA="
set /p "OTRA=   Enter para dejar %CUENTA%, o escriba DOMINIO\usuario: "
if not "%OTRA%"=="" set "CUENTA=%OTRA%"
echo.
echo   La tarea va a correr con:  %CUENTA%
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
  echo     1. Si dijo 'Acceso denegado': hace falta abrir esta ventana
  echo        como administrador. Clic derecho sobre el archivo -
  echo        Ejecutar como administrador.
  echo        Y si al elevarla Windows le pide OTRA cuenta, cuando este
  echo        archivo le pregunte con que cuenta correr, escriba la del
  echo        motor, no la de administrador.
  echo     2. Si dijo que la contrasena no sirve: vuelva a intentar. Ojo
  echo        con el bloqueo de mayusculas.
  echo.
  echo   OJO IMPORTANTE: al crear la tarea se borra primero la que
  echo   hubiera. Si ya existia una y esto fallo, AHORA NO HAY NINGUNA:
  echo   el motor NO va a arrancar solo al prender el PC hasta que este
  echo   archivo termine bien. Compruebelo con tools\ESTADO_MOTOR.cmd.
  echo.
  echo   El motor sigue arrancando al iniciar sesion, eso no se toco.
  echo.
  pause
  exit /b 1
)

rem ---------- 3b) El autodespliegue tambien sin sesion ----------
rem  POR QUE (21-08-2026, tarde). El autodespliegue corre cada 5
rem  minutos y trae una RED DE SEGURIDAD: si el motor no esta
rem  arriba, lo arranca directo. Es lo que ha salvado el portal
rem  varias veces.
rem
rem  Pero esa tarea se creo sin decir con que cuenta corre, y
rem  Windows por defecto la deja en 'solo cuando el usuario haya
rem  iniciado sesion'. O sea: la red de seguridad dormia justo
rem  cuando mas hacia falta, al prender el PC sin que nadie entre.
rem  Se reinicio el equipo esa tarde, el motor no arranco, y la red
rem  de seguridad no se entero.
rem
rem  Se vuelve a crear con la misma cuenta, para que trabaje igual
rem  este quien este. Windows pide la contrasena OTRA VEZ: es la
rem  misma de antes, y se guarda en la boveda de Windows, nunca en
rem  un archivo de este repositorio.
echo.
echo   Ahora la tarea del autodespliegue, para que la red de
echo   seguridad tambien trabaje con el PC recien prendido.
echo   Windows le pide la MISMA contrasena una segunda vez.
echo.
schtasks /Create /F /TN "MotorGlosas_Autodeploy" /SC MINUTE /MO 5 ^
  /RU "%CUENTA%" /RP * /TR "\"%REPO%\tools\autodeploy_motor_local.cmd\""
if errorlevel 1 (
  echo.
  echo   OJO: no se pudo cambiar la tarea del autodespliegue.
  echo   El arranque del PC SI quedo puesto y el motor va a subir.
  echo   Lo unico que falta es la red de seguridad cuando nadie ha
  echo   iniciado sesion. Se puede reintentar corriendo este mismo
  echo   archivo mas tarde. No se rompio nada.
  echo.
) else (
  echo    Autodespliegue con red de seguridad permanente: listo.
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
echo.
echo     Corre con la cuenta:  %CUENTA%
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
