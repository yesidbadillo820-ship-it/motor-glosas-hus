@echo off
rem Instala la tarea programada que ejecuta el organizador cada 15 minutos.
rem Ejecutar UNA VEZ como el usuario que tiene la unidad Z: y las variables
rem GLOSAS_IMAP_* configuradas (ver README_organizar_correos_glosas.md).
rem La tarea apunta a organizador_tarea.bat, que deja log en organizador_tarea.log
chcp 65001 >nul
set "TAREA=HUS Organizador Correos Glosas"

schtasks /create /f /tn "%TAREA%" /sc minute /mo 15 /tr "\"%~dp0organizador_tarea.bat\""

if %ERRORLEVEL%==0 (
  echo.
  echo Tarea "%TAREA%" creada: corre cada 15 minutos.
  echo Para probarla ya:      schtasks /run /tn "%TAREA%"
  echo Para desinstalarla:    schtasks /delete /tn "%TAREA%" /f
) else (
  echo.
  echo ERROR: no se pudo crear la tarea. Ejecuta esta ventana como Administrador
  echo o crea la tarea manualmente en el Programador de tareas de Windows
  echo apuntando a: %~dp0organizador_tarea.bat
)
pause
