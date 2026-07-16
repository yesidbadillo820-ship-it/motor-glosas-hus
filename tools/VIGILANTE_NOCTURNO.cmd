@echo off
REM ====================================================================
REM  VIGILANTE_NOCTURNO.cmd  -  Bot del Motor Glosas HUS.
REM  Deja programada una tarea de Windows que TODAS LAS NOCHES convierte
REM  los .txt nuevos de la carpeta que elijas (a .csv por comas + Excel),
REM  sin que nadie le de doble clic. Usa el motor de TXT_A_EXCEL.cmd
REM  (debe estar junto a este bot al instalar).
REM
REM  La tarea corre como tu usuario y solo si el PC esta encendido con
REM  la sesion iniciada. Todo queda anotado en VIGILANTE_LOG.txt.
REM  USO: doble clic -> opcion 1 para instalar.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title VIGILANTE NOCTURNO - Motor Glosas HUS

:inicio
cls
echo.
echo  ============================================================
echo    VIGILANTE NOCTURNO  -  conversion automatica cada noche
echo  ============================================================
echo.
schtasks /query /tn "MotorGlosasHUS_Nocturno" >nul 2>&1 && echo   Estado: tarea INSTALADA (se puede actualizar o quitar) || echo   Estado: tarea no instalada
echo.
echo    1. Instalar o actualizar la tarea nocturna
echo    2. Probar ahora (correr una vez y ver el resultado)
echo    3. Desinstalar la tarea
echo    0. Salir
echo.
set "OP="
set /p "OP=  Elige una opcion y presiona Enter: "
if "%OP%"=="1" goto instalar
if "%OP%"=="2" goto probar
if "%OP%"=="3" goto desinstalar
if "%OP%"=="0" exit /b 0
goto inicio

:instalar
if not exist "%~dp0TXT_A_EXCEL.cmd" (
  echo.
  echo   [ERROR] Falta TXT_A_EXCEL.cmd junto a este bot: de ahi se saca el
  echo           motor de conversion. Copialo a esta carpeta y reintenta.
  echo.
  pause
  goto inicio
)
set "DEFCARP=%~dp0"
if "%DEFCARP:~-1%"=="\" set "DEFCARP=%DEFCARP:~0,-1%"
set "CARPETA=%DEFCARP%"
echo.
echo   Carpeta a vigilar cada noche (Enter para usar la de este .cmd):
setlocal EnableDelayedExpansion
echo   [!CARPETA!]
endlocal
set /p "CARPETA=  Ruta: "
set "CARPETA=%CARPETA:"=%"
if not defined CARPETA set "CARPETA=%DEFCARP%"
:quitarbs
if "%CARPETA:~-1%"=="\" ( set "CARPETA=%CARPETA:~0,-1%" & goto quitarbs )
if not defined CARPETA set "CARPETA=%DEFCARP%"
if "%CARPETA:~-1%"==":" set "CARPETA=%CARPETA%/"
set "HORA=19:00"
set /p "HORA=  Hora de la corrida (HH:MM, Enter = 19:00): "
echo %HORA%|findstr /r "^[0-2][0-9]:[0-5][0-9]$" >nul || set "HORA=19:00"
echo.
REM --- sacar el motor de conversion desde TXT_A_EXCEL.cmd -------------
set "ORIGENCMD=%~dp0TXT_A_EXCEL.cmd"
set "MOTOR=%~dp0motor_nocturno.py"
del "%MOTOR%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if not exist "%MOTOR%" (
  echo   [ERROR] No se pudo preparar el motor de conversion.
  echo.
  pause
  goto inicio
)
REM --- sacar RUN_NOCTURNO.cmd de este mismo archivo -------------------
set "ORIGENCMD=%~f0"
set "RUNCMD=%~dp0RUN_NOCTURNO.cmd"
del "%RUNCMD%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#RUN'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:RUNCMD -Encoding ASCII"
if not exist "%RUNCMD%" (
  echo   [ERROR] No se pudo preparar RUN_NOCTURNO.cmd.
  echo.
  pause
  goto inicio
)
>"%~dp0VIGILANTE_CONFIG.txt" echo %CARPETA%
schtasks /create /f /tn "MotorGlosasHUS_Nocturno" /tr "\"%RUNCMD%\"" /sc daily /st %HORA% >nul 2>&1
if errorlevel 1 (
  echo   [ERROR] Windows no dejo crear la tarea programada en este equipo.
  echo           Pidele a Sistemas que permita "schtasks" para tu usuario.
  echo.
  pause
  goto inicio
)
echo   [OK] Tarea instalada: todas las noches a las %HORA% se convierten
echo        los .txt nuevos de: %CARPETA%
echo        Registro de cada corrida: VIGILANTE_LOG.txt
echo.
pause
goto inicio

:probar
if not exist "%~dp0RUN_NOCTURNO.cmd" (
  echo.
  echo   [!] Primero instala la tarea (opcion 1).
  echo.
  pause
  goto inicio
)
echo.
echo   Corriendo una vez, espera...
call "%~dp0RUN_NOCTURNO.cmd"
echo   Listo: revisa VIGILANTE_LOG.txt para ver el detalle.
echo.
pause
goto inicio

:desinstalar
schtasks /delete /f /tn "MotorGlosasHUS_Nocturno" >nul 2>&1
echo.
echo   Tarea eliminada. (RUN_NOCTURNO.cmd y el motor quedan por si la
echo   vuelves a instalar; puedes borrarlos si no los quieres.)
echo.
pause
goto inicio

REM ====================================================================
REM  Script de la corrida nocturna (se extrae como RUN_NOCTURNO.cmd).
REM ====================================================================
#RUNSTART#
@echo off
REM RUN_NOCTURNO.cmd - lo lanza la tarea programada MotorGlosasHUS_Nocturno.
setlocal EnableExtensions DisableDelayedExpansion
set "CARPETA="
if exist "%~dp0VIGILANTE_CONFIG.txt" set /p CARPETA=<"%~dp0VIGILANTE_CONFIG.txt"
set "LOG=%~dp0VIGILANTE_LOG.txt"
if not defined CARPETA (
  >>"%LOG%" echo %DATE% %TIME:~0,8% ERROR: sin VIGILANTE_CONFIG.txt
  exit /b 2
)
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE (
  >>"%LOG%" echo %DATE% %TIME:~0,8% ERROR: no hay Python instalado
  exit /b 1
)
>>"%LOG%" echo ================ %DATE% %TIME:~0,8% ================
%PYEXE% "%~dp0motor_nocturno.py" "%CARPETA%" >>"%LOG%" 2>&1
exit /b 0
