@echo off
REM ============================================================================
REM  HACER TODO COOSALUD.bat — doble clic y responde las preguntas.
REM  Toda la logica vive en coosalud_todo.py (debe estar en esta misma carpeta
REM  junto a organizar_cargue_masivo_coosalud.py y consolidar_coosalud.py).
REM ============================================================================
@chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"
"%PYEXE%" "%~dp0coosalud_todo.py"
