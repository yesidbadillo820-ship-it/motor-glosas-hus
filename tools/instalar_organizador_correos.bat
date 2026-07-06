@echo off
rem Instala la tarea programada que ejecuta el organizador cada 15 minutos.
rem Ejecutar UNA VEZ como el usuario que tiene la unidad Z: y las variables
rem GLOSAS_IMAP_* configuradas (ver README_organizar_correos_glosas.md).
chcp 65001 >nul
set TAREA=HUS Organizador Correos Glosas
set SCRIPT=%~dp0organizar_correos_glosas.py

schtasks /create /f /tn "%TAREA%" /sc minute /mo 15 ^
  /tr "cmd /c cd /d \"%~dp0\" && py \"%SCRIPT%\" >> \"%~dp0organizador_tarea.log\" 2>&1"

if %ERRORLEVEL%==0 (
  echo.
  echo Tarea "%TAREA%" creada: corre cada 15 minutos.
  echo Para probarla ya:      schtasks /run /tn "%TAREA%"
  echo Para desinstalarla:    schtasks /delete /tn "%TAREA%" /f
) else (
  echo.
  echo ERROR: no se pudo crear la tarea. Ejecuta esta ventana como Administrador
  echo o crea la tarea manualmente en el Programador de tareas de Windows.
)
pause
