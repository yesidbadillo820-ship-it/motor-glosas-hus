@echo off
chcp 65001 >nul
title Norsk - curso de noruego
rem Se para SOLO en la carpeta del repositorio: sin esto, "python -m noruego"
rem falla con "No module named noruego" si la consola esta en otra carpeta.
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] No se encontro Python en este computador.
  echo Instalalo desde https://www.python.org/downloads/ y marca
  echo la casilla "Add Python to PATH" durante la instalacion.
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo   NORSK - CURSO DE NORUEGO
echo ============================================================
echo.
echo Generando la aplicacion...
python -m noruego exportar
if errorlevel 1 ( echo. & echo [ERROR] No se pudo generar. & pause & exit /b 1 )

echo.
echo ============================================================
echo   PARA USARLA EN EL CELULAR
echo ============================================================
echo.
echo Esta es la direccion de este computador en la red:
ipconfig ^| findstr /C:"IPv4"
echo.
echo 1. Deja esta ventana abierta.
echo 2. En el celular, conectado al MISMO wifi, abre el navegador y escribe:
echo.
echo      http://LA-IP-DE-ARRIBA:8000/static/noruego/index.html
echo.
echo 3. En el menu del navegador toca "Agregar a la pantalla de inicio".
echo    Desde ahi abre como una aplicacion y funciona sin internet.
echo.
echo Presiona una tecla para levantar el servidor (Ctrl+C para pararlo).
pause >nul
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
