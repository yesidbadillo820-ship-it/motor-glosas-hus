@echo off
rem Corrida manual del organizador de correos de glosas.
rem Requiere GLOSAS_IMAP_USER / GLOSAS_IMAP_PASSWORD (ver README_organizar_correos_glosas.md)
chcp 65001 >nul
cd /d "%~dp0"
py organizar_correos_glosas.py %*
echo.
echo Codigo de salida: %ERRORLEVEL%
pause
