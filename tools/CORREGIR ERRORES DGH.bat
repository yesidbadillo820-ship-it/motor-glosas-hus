@echo off
REM ============================================================================
REM  CORREGIR ERRORES DGH.bat — doble clic despues de que DGH devuelva errores.
REM  Pide el Excel de ERRORES de DGH y el OBJECIONES que se subio, y arma el
REM  "OBJECIONES ... REINTENTO.xlsx" listo para volver a cargar.
REM  Necesita corregir_errores_dgh.py y consolidar_coosalud.py en esta carpeta.
REM ============================================================================
@chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=py"
where py >nul 2>nul || set "PYEXE=python"
"%PYEXE%" "%~dp0corregir_errores_dgh.py"
