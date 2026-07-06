@echo off
rem Runner de la tarea programada: corre el organizador y deja log.
rem No ejecutar a mano (no muestra pausa); para eso esta organizar_correos_glosas.bat
chcp 65001 >nul
cd /d "%~dp0"
py organizar_correos_glosas.py >> "%~dp0organizador_tarea.log" 2>&1
