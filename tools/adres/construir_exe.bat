@echo off
setlocal
title Construir ejecutables (.exe) - Herramientas ADRES

REM --- Detectar el comando de Python (py o python) ---
set PYCMD=
py --version >nul 2>&1 && set PYCMD=py
if not defined PYCMD ( python --version >nul 2>&1 && set PYCMD=python )
if not defined PYCMD (
  echo [ERROR] No encontre Python. Instalalo y corre INSTALAR.bat
  pause
  exit /b 1
)

echo ============================================
echo   Construir .EXE autonomos (corren SIN Python)
echo ============================================
echo.
echo Se construye UNA vez en esta PC (que tiene Python).
echo Luego copia la carpeta dist\ a cualquier Windows y los
echo .exe funcionan SIN instalar nada.
echo.

echo Instalando PyInstaller...
%PYCMD% -m pip install --quiet --upgrade pyinstaller openpyxl
if errorlevel 1 (
  echo [ERROR] No pude instalar PyInstaller. Revisa tu internet.
  pause
  exit /b 1
)

set OPTS=--onefile --console --clean --noconfirm --distpath "%~dp0dist" --workpath "%~dp0build" --specpath "%~dp0build" --paths "%~dp0"

echo.
echo [1/3] generar_fur.exe ...
%PYCMD% -m PyInstaller %OPTS% --hidden-import fur_lectura --hidden-import rips_lectura --hidden-import factura_lectura --name generar_fur "%~dp0generar_fur.py"

echo [2/3] generar_fur_servicios.exe ...
%PYCMD% -m PyInstaller %OPTS% --hidden-import rips_lectura --hidden-import factura_lectura --hidden-import furips_lectura --hidden-import cups_catalogo --name generar_fur_servicios "%~dp0generar_fur_servicios.py"

echo [3/3] inspeccionar_soportes.exe ...
%PYCMD% -m PyInstaller %OPTS% --hidden-import rips_lectura --hidden-import factura_lectura --name inspeccionar_soportes "%~dp0inspeccionar_soportes.py"

echo.
echo ============================================
echo   Listo. Los .exe estan en:
echo   %~dp0dist
echo ============================================
echo.
echo Ejemplo de uso en la otra PC (sin Python):
echo   generar_fur.exe --fur "FURIPS1....txt" --salida "lote_FUR.xlsx"
echo.
pause
endlocal
