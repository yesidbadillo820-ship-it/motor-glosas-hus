@echo off
setlocal
title Instalar dependencias - Herramientas ADRES

echo ============================================
echo   Instalacion de dependencias (una sola vez)
echo ============================================
echo.

REM --- Detectar el comando de Python (py o python) ---
set PYCMD=
py --version >nul 2>&1 && set PYCMD=py
if not defined PYCMD ( python --version >nul 2>&1 && set PYCMD=python )

if not defined PYCMD (
  echo [ERROR] No encontre Python en esta PC.
  echo.
  echo Instala Python 3 desde:  https://www.python.org/downloads/
  echo IMPORTANTE: en el instalador marca la casilla "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

echo Python detectado (comando: %PYCMD%):
%PYCMD% --version
echo.

echo Actualizando pip...
%PYCMD% -m pip install --upgrade pip >nul 2>&1

echo Instalando librerias (openpyxl)...
%PYCMD% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo.
  echo [ERROR] Fallo la instalacion de librerias.
  echo Revisa tu conexion a internet e intenta de nuevo.
  pause
  exit /b 1
)

echo.
echo ============================================
echo   Listo. Ya podes usar las herramientas:
echo     - doble clic en GENERAR_FUR.bat
echo ============================================
pause
endlocal
