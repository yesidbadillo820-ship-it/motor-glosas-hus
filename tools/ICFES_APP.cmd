@echo off
chcp 65001 >nul
title Preparacion ICFES Saber 11
cd /d %~dp0..
echo ============================================================
echo   PREPARACION ICFES SABER 11
echo   Genera la aplicacion y la abre en el navegador.
echo   Funciona sin internet.
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] No se encontro Python en este computador.
  echo Instalalo desde https://www.python.org/downloads/ y marca
  echo la casilla "Add Python to PATH" durante la instalacion.
  echo.
  pause
  exit /b 1
)

echo Generando la aplicacion...
python -m icfes exportar-web --salida "%USERPROFILE%\Desktop\ICFES.html"
if errorlevel 1 (
  echo.
  echo [ERROR] No se pudo generar la aplicacion.
  pause
  exit /b 1
)

echo.
echo Listo. Se guardo en el Escritorio como ICFES.html
echo Abriendo...
start "" "%USERPROFILE%\Desktop\ICFES.html"
echo.
echo De aqui en adelante puedes abrirla con doble clic en ese archivo,
echo sin volver a correr este bot y sin internet.
echo.
pause
