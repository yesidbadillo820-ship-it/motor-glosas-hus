@echo off
chcp 65001 >nul
title Preparacion ICFES Saber 11
rem Este bot se para SOLO en la carpeta del repositorio (la de arriba de tools\).
rem Sin esto, "python -m icfes" falla con "No module named icfes" cuando la
rem consola esta parada en otra carpeta, que es el error mas comun.
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

:menu
cls
echo ============================================================
echo   PREPARACION ICFES SABER 11
echo ============================================================
python -m icfes hoy 2>nul | findstr /C:"Faltan" /C:"Falta " /C:"El examen"
echo.
echo   1. Que estudiar hoy
echo   2. Practicar preguntas
echo   3. Repasar lo que vence hoy
echo   4. Simulacro (con cronometro)
echo   5. Ver mi progreso
echo   6. Ver el plan completo
echo   7. Configurar fecha del examen y meta
echo   8. Generar la aplicacion web (funciona sin internet)
echo   9. Salir
echo.
set "opcion="
set /p opcion=Escoge una opcion (1-9):

if "%opcion%"=="1" (python -m icfes hoy & goto pausa)
if "%opcion%"=="2" goto practicar
if "%opcion%"=="3" (python -m icfes repaso & goto pausa)
if "%opcion%"=="4" goto simulacro
if "%opcion%"=="5" (python -m icfes progreso & goto pausa)
if "%opcion%"=="6" (python -m icfes plan & goto pausa)
if "%opcion%"=="7" goto configurar
if "%opcion%"=="8" goto exportar
if "%opcion%"=="9" exit /b 0
goto menu

:practicar
echo.
echo   Areas:  lc = Lectura Critica    mat = Matematicas    soc = Sociales
echo           cn = Ciencias Naturales ing = Ingles         (vacio = todas)
echo.
set "area="
set /p area=Area:
set "cuantas="
set /p cuantas=Cuantas preguntas (Enter para 10):
if "%cuantas%"=="" set "cuantas=10"
if "%area%"=="" (
  python -m icfes practicar -n %cuantas%
) else (
  python -m icfes practicar --area %area% -n %cuantas%
)
goto pausa

:simulacro
echo.
echo   1. Examen completo (las cinco areas)  ^<- empieza por este
echo   2. Sesion 1 (Lectura Critica + Mat + Soc + Naturales)
echo   3. Sesion 2 (Ingles + Mat + Soc + Naturales)
echo.
set "tipo="
set /p tipo=Tipo (1-3):
if "%tipo%"=="2" (python -m icfes simulacro --tipo sesion1 & goto pausa)
if "%tipo%"=="3" (python -m icfes simulacro --tipo sesion2 & goto pausa)
python -m icfes simulacro --tipo completo
goto pausa

:configurar
echo.
set "fecha="
set /p fecha=Fecha del examen en formato 2027-08-08:
set "meta="
set /p meta=Meta de puntaje global de 0 a 500 (Enter para 400):
if "%meta%"=="" set "meta=400"
set "horas="
set /p horas=Horas de estudio por semana (Enter para 12):
if "%horas%"=="" set "horas=12"
python -m icfes iniciar --examen %fecha% --meta %meta% --horas %horas%
goto pausa

:exportar
python -m icfes exportar-web --salida "%USERPROFILE%\Desktop\ICFES.html"
if errorlevel 1 goto pausa
echo.
echo Se guardo en el Escritorio como ICFES.html
start "" "%USERPROFILE%\Desktop\ICFES.html"
goto pausa

:pausa
echo.
pause
goto menu
