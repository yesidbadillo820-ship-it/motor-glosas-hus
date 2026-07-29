@echo off
rem Runner de la tarea programada: corre el organizador y deja log.
rem No ejecutar a mano (no muestra pausa); para eso esta organizar_correos_glosas.bat
chcp 65001 >nul
cd /d "%~dp0"
rem El log no debe crecer sin limite: si supera ~5 MB se reinicia
if exist "%~dp0organizador_tarea.log" (
  for %%s in ("%~dp0organizador_tarea.log") do if %%~zs gtr 5000000 del "%~dp0organizador_tarea.log"
)
py organizar_correos_glosas.py >> "%~dp0organizador_tarea.log" 2>&1
