@echo off
setlocal enabledelayedexpansion
title Generar FUR (ADRES)

REM --- Detectar el comando de Python (py o python) ---
set PYCMD=
py --version >nul 2>&1 && set PYCMD=py
if not defined PYCMD ( python --version >nul 2>&1 && set PYCMD=python )
if not defined PYCMD (
  echo [ERROR] No encontre Python. Corre primero INSTALAR.bat
  pause
  exit /b 1
)

echo ============================================
echo   Generador del FUR (62 campos ADRES)
echo ============================================
echo.
echo Arrastra aqui el archivo del HUS (FURIPS1...txt o .xlsx)
echo y presiona Enter:
echo.
set "FUR="
set /p "FUR=> "
REM Quitar comillas que agrega Windows al arrastrar
set "FUR=!FUR:"=!"

if not exist "!FUR!" (
  echo.
  echo [ERROR] No encontre el archivo:
  echo   !FUR!
  pause
  exit /b 1
)

REM La salida queda JUNTO al archivo de entrada, como lote_FUR.xlsx
for %%F in ("!FUR!") do set "SALIDA=%%~dpFlote_FUR.xlsx"

echo.
echo Generando... (esto puede tardar segundos)
echo.
%PYCMD% "%~dp0generar_fur.py" --fur "!FUR!" --salida "!SALIDA!"

echo.
echo ============================================
echo   Excel generado en:
echo   !SALIDA!
echo ============================================
pause
endlocal
