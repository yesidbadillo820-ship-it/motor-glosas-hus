@echo off
rem ================================================================
rem  TUNEL de Cloudflare en modo SIN DOCKER: publica la pagina
rem  https://iaglosassinac.help apuntando al servidor local.
rem  Usa el token guardado en el .env (linea TUNNEL_TOKEN=).
rem  Si el tunel se cae, se reconecta solo a los 5 segundos.
rem  Registro en data\tunel.log
rem ================================================================
setlocal
title MotorGlosasTunel
set "BASE=C:\motor-glosas"
set "REPO=%BASE%\repo"
if not exist "%BASE%\cloudflared.exe" exit /b 1

rem Si ya hay un tunel corriendo, no duplicar
tasklist /fi "IMAGENAME eq cloudflared.exe" 2>nul | find /i "cloudflared.exe" >nul && exit /b 0

set "TOKEN="
for /f "tokens=1* delims==" %%a in ('findstr /b "TUNNEL_TOKEN=" "%REPO%\.env"') do set "TOKEN=%%b"
if "%TOKEN%"=="" exit /b 1
set "LOG=%REPO%\data\tunel.log"

rem Protocolo de salida. Por defecto cloudflared usa QUIC (UDP al puerto
rem 7844) y la red del hospital lo bloquea: el 04-08-2026 la pagina se
rem cayo con "Error 1033" y el propio diagnostico de cloudflared lo dejo
rem escrito: "UDP Connectivity: QUIC connection failed" y "TCP
rem Connectivity: HTTP/2 connection successful". Con http2 sale por TCP,
rem que si pasa. Si algun dia se abre el UDP, poner CF_PROTOCOLO=quic
rem (o auto) como variable de entorno antes de arrancar.
set "PROTOCOLO=%CF_PROTOCOLO%"
if "%PROTOCOLO%"=="" set "PROTOCOLO=http2"

:loop
for %%s in ("%LOG%") do if %%~zs GTR 5000000 del "%LOG%" >nul 2>&1
echo [%date% %time%] conectando el tunel (protocolo %PROTOCOLO%)... >> "%LOG%"
"%BASE%\cloudflared.exe" tunnel --no-autoupdate --protocol %PROTOCOLO% run --token %TOKEN% >> "%LOG%" 2>&1
echo [%date% %time%] el tunel se corto; se reconecta en 5 segundos >> "%LOG%"
rem  ESPERAS CON PING, NO CON TIMEOUT (21-08-2026). Estos bots ahora
rem  corren tambien SIN sesion iniciada (tarea de arranque del PC), y
rem  ahi `timeout` no siempre tiene una consola de verdad: contesta
rem  "Input redirection is not supported" y sigue de largo sin esperar,
rem  con lo que el bucle se vuelve loco. `ping` a uno mismo espera
rem  igual y funciona en todos los casos. ping -n 6 = 5 segundos.
ping -n 6 127.0.0.1 >nul
goto :loop
