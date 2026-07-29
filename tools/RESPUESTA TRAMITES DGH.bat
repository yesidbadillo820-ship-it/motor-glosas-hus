@echo off
REM ============================================================================
REM  RESPUESTA TRAMITES DGH.bat — ultimo paso del ciclo COOSALUD.
REM  Toma el export de tramites de DGH (PARA CARGUE DE TRAMITES COOSALUD.xlsx)
REM  y le agrega FECHA DE CARGUE, CODIGO RESPUESTA (RE9502/RE9901),
REM  VALOR ACEPTADO y OBSERVACION, listo para subirlo a DGH.
REM  Necesita respuesta_tramites_dgh.py y consolidar_coosalud.py juntos.
REM ============================================================================
@chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"
"%PYEXE%" "%~dp0respuesta_tramites_dgh.py"
