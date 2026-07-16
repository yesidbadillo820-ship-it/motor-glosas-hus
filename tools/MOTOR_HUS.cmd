@echo off
REM ====================================================================
REM  MOTOR_HUS.cmd  -  Menu unico de los bots del Motor Glosas HUS.
REM  Pon este menu (y los bots) en una carpeta, dale doble clic y elige
REM  con un numero. Cada uso queda anotado en REGISTRO_BOTS.csv (fecha,
REM  usuario, equipo y bot) para el informe de gerencia.
REM  USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title MOTOR GLOSAS HUS - Menu de bots

:inicio
cls
echo.
echo  ============================================================
echo    MOTOR GLOSAS HUS  -  menu de bots de auditoria
echo  ============================================================
echo.
echo    1. Une los PDF de cada carpeta (y deja copia .cmd)
echo    2. Copia .cmd de cada PDF individual
echo    3. Copia .cmd de cada Excel
echo    4. Baja el peso de los .zip
echo    5. Parte .zip en pedazos de menos de 30 MB
echo    6. Cada .txt queda como .csv por comas + Excel
echo    7. Cada Excel queda como .csv por comas
echo    8. Saca la info de contrato de los XML (glosas)
echo    9. Chequea el lote ANTES de radicar
echo   10. Cruza el Excel de la EPS con los XML + borradores
echo   11. Plazos de respuesta en dias habiles
echo   12. Recolecta los soportes de una lista de facturas
echo   13. Informe para gerencia (desde la bitacora)
echo   14. Tarea nocturna: convierte los .txt solos
echo   15. Audita devoluciones EPS (DGH vs RIPS vs soportes)
echo.
echo    0. Salir
echo.
set "OP="
set /p "OP=  Elige una opcion y presiona Enter: "
if "%OP%"=="0" exit /b 0
if "%OP%"=="1" ( call :lanzar UNIR_PDFS.cmd & goto inicio )
if "%OP%"=="2" ( call :lanzar PDF_A_CMD.cmd & goto inicio )
if "%OP%"=="3" ( call :lanzar EXCEL_A_CMD.cmd & goto inicio )
if "%OP%"=="4" ( call :lanzar COMPRIMIR_ZIP.cmd & goto inicio )
if "%OP%"=="5" ( call :lanzar PARTIR_ZIP_30MB.cmd & goto inicio )
if "%OP%"=="6" ( call :lanzar TXT_A_EXCEL.cmd & goto inicio )
if "%OP%"=="7" ( call :lanzar EXCEL_A_CSV.cmd & goto inicio )
if "%OP%"=="8" ( call :lanzar REVISAR_XML.cmd & goto inicio )
if "%OP%"=="9" ( call :lanzar VERIFICAR_RADICACION.cmd & goto inicio )
if "%OP%"=="10" ( call :lanzar CRUZAR_GLOSAS.cmd & goto inicio )
if "%OP%"=="11" ( call :lanzar SEMAFORO_GLOSAS.cmd & goto inicio )
if "%OP%"=="12" ( call :lanzar BUSCAR_FACTURA.cmd & goto inicio )
if "%OP%"=="13" ( call :lanzar INFORME_GERENCIA.cmd & goto inicio )
if "%OP%"=="14" ( call :lanzar VIGILANTE_NOCTURNO.cmd & goto inicio )
if "%OP%"=="15" ( call :lanzar AUDITAR_DEV_EPS.cmd & goto inicio )
echo.
echo   [!] Opcion no valida. Intenta de nuevo...
timeout /t 2 >nul
goto inicio

:lanzar
set "BOT=%~1"
if not exist "%~dp0%BOT%" (
  echo.
  echo   [!] No encuentro %BOT% en esta carpeta.
  echo       Copia ese bot junto a este menu y vuelve a intentar.
  echo.
  pause
  goto :eof
)
if not exist "%~dp0REGISTRO_BOTS.csv" >"%~dp0REGISTRO_BOTS.csv" echo fecha;hora;usuario;equipo;bot
>>"%~dp0REGISTRO_BOTS.csv" echo %DATE%;%TIME:~0,8%;%USERNAME%;%COMPUTERNAME%;%BOT%
call "%~dp0%BOT%"
goto :eof
