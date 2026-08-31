@echo off
chcp 65001 >nul
title Norsk - curso de noruego
rem Se para SOLO en la carpeta del repositorio: sin esto, "python -m noruego"
rem falla con "No module named noruego" si la consola esta en otra carpeta.
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] No se encontro Python en este computador.
  echo Instalalo desde https://www.python.org/downloads/ y marca
  echo la casilla "Add Python to PATH" durante la instalacion.
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo   NORSK - CURSO DE NORUEGO
echo ============================================================
echo.
echo Generando la aplicacion...
python -m noruego exportar
if errorlevel 1 ( echo. & echo [ERROR] No se pudo generar. & pause & exit /b 1 )

rem --- El enlace exacto para el celular ---
rem Lo arma Python, no este archivo: en un PC con VirtualBox o WSL, ipconfig
rem lista varias direcciones y ninguna dice cual es la del wifi.
rem OJO con el "^|": dentro de un for /f va escapado, pero suelto en una
rem linea normal el "|" le llega a ipconfig como argumento y el bot muestra
rem la ayuda de ipconfig en vez de la direccion. Paso de verdad el 31-08.
set "ENLACE="
for /f "tokens=*" %%A in ('python -m noruego direccion') do set "ENLACE=%%A"

echo.
echo ============================================================
echo   PARA USARLA EN EL CELULAR
echo ============================================================
echo.
echo 1. Deja esta ventana abierta.
echo.
if not defined ENLACE goto :sin_enlace
echo 2. En el CELULAR, con el MISMO wifi de este computador, abre el
echo    navegador y escribe esta direccion TAL CUAL, letra por letra
echo    (no la busques en Google, va en la barra de arriba):
echo.
echo       %ENLACE%
echo.
echo    Si esa no sirve, este computador tiene mas de una direccion.
echo    Prueba con los otros numeros de esta lista, en el mismo formato:
ipconfig | findstr /C:"IPv4"
goto :instalar

:sin_enlace
echo 2. No se pudo averiguar la direccion de este computador.
echo    Abre otra ventana, escribe  ipconfig  y busca la linea "IPv4".
echo    Ese numero (algo como 192.168.1.15) reemplaza a ESE-NUMERO:
echo.
echo       http://ESE-NUMERO:8000/static/noruego/index.html
echo.
echo    Escribelo en el navegador del CELULAR, con el mismo wifi.
ipconfig | findstr /C:"IPv4"

:instalar
echo.
echo 3. Para que quede como una aplicacion en el celular:
echo    - Android (Chrome): toca los tres puntos de arriba a la derecha
echo      y elige "Agregar a la pantalla principal" o "Instalar aplicacion".
echo    - iPhone (Safari): toca el boton de compartir, el cuadrito con la
echo      flecha hacia arriba, y elige "Anadir a pantalla de inicio".
echo    Desde ahi abre sola y funciona sin internet.
echo.
echo    OJO: eso es del CELULAR. En este computador no busques
echo    "Agregar a la pantalla de inicio", aqui basta con abrir
echo    static\noruego\index.html con doble clic.
echo.
echo ------------------------------------------------------------
echo   SI EL CELULAR DICE "TARDO DEMASIADO EN RESPONDER"
echo ------------------------------------------------------------
echo El enlace esta bien: lo que pasa es que el celular no llega
echo hasta este computador. Casi siempre es una de estas tres:
echo.
echo  a) El firewall de Windows bloquea el puerto. Abre PowerShell
echo     COMO ADMINISTRADOR y pega esta linea (una sola vez):
echo.
echo        New-NetFirewallRule -DisplayName "Curso noruego" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any
echo.
echo  b) El celular esta en otra red. Si este computador esta por
echo     cable y el celular en el wifi de invitados, no se ven.
echo.
echo  c) La red del hospital separa el wifi del cable. En ese caso
echo     use la direccion con la que entra al Motor de Glosas desde
echo     afuera y cambiele el final por:
echo        /static/noruego/index.html
echo     El mismo servidor sirve la aplicacion, sin firewall ni wifi.
echo.
echo Presiona una tecla para levantar el servidor (Ctrl+C para pararlo).
pause >nul
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
