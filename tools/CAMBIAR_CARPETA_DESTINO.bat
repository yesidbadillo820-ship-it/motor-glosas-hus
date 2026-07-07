@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo ============================================
echo    Cambiar carpeta destino del BOT
echo ============================================
echo.
if "%GLOSAS_BASE%"=="" (
  echo Destino actual: EL SERVIDOR DE GLOSAS - Z:\SERVIDOR GLOSAS\...
) else (
  echo Destino actual: %GLOSAS_BASE%
)
echo.
echo Escribe la carpeta de PRUEBAS donde el bot debe archivar
echo   ejemplo: D:\USUARIO CARTERA\Documents\PRUEBAS MAIL
echo o deja VACIO y presiona Enter para volver al servidor real.
echo.
set "NUEVA="
set /p NUEVA="Carpeta destino: "

if "!NUEVA!"=="" (
  reg delete "HKCU\Environment" /v GLOSAS_BASE /f >nul 2>&1
  echo.
  echo [OK] El bot vuelve a archivar en el SERVIDOR DE GLOSAS - Z:
) else (
  if not exist "!NUEVA!" mkdir "!NUEVA!"
  setx GLOSAS_BASE "!NUEVA!" >nul
  echo.
  echo [OK] El bot archivara en: !NUEVA!
)
echo.
echo El cambio aplica desde la PROXIMA corrida de la tarea programada
echo y en cualquier consola nueva. El registro y el estado quedan en
echo la subcarpeta "00-CONTROL AUTOMATICO" del destino elegido.
echo.
echo OJO: al cambiar de destino, el bot vuelve a archivar alli los
echo correos de los ultimos 3 dias (cada destino lleva su propia
echo memoria de que ya proceso). Eso es lo esperado para probar.
pause
