@echo off
REM ====================================================================
REM  CARGAR_SIIFA.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Todo el cargue de respuestas a SIIFA (Ministerio de Salud) en un
REM  solo menu: bajar el informe, armar los archivos de respuestas,
REM  piloto de 1 glosa y cargue masivo con reporte.
REM
REM  Se instala solo Python y sus componentes si faltan. USO: doble clic.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title CARGAR RESPUESTAS EN SIIFA - Motor Glosas HUS
cd /d "%~dp0.."

echo.
echo ============================================================
echo   CARGAR RESPUESTAS EN SIIFA - E.S.E. HUS
echo ============================================================
echo.

REM --- 1) Buscar Python (validando por ejecucion) ---------------------
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

:deps
REM --- 2) Asegurar los componentes (Excel y conexion) -----------------
%PYEXE% -c "import openpyxl, httpx" >nul 2>&1 && goto credenciales
echo [i] Instalando los componentes por unica vez, espera...
%PYEXE% -m pip install --quiet --user openpyxl httpx >nul 2>&1
%PYEXE% -c "import openpyxl, httpx" >nul 2>&1 && goto credenciales
echo [ATENCION] No quedaron instalados (revisa el internet del equipo).
echo.

:credenciales
REM --- 3) Usuario y clave de SIIFA (nunca se escriben en el codigo) ---
if defined SIIFA_USER if defined SIIFA_PASSWORD goto carpeta
echo   Falta el usuario y la clave de SIIFA (los del portal del Ministerio).
echo   Quedan guardados en este equipo, no se escriben en ningun archivo.
echo.
set /p "SIIFA_USER=  Usuario SIIFA: "
REM La clave se pide oculta (no queda escrita en la pantalla).
for /f "delims=" %%P in ('powershell -NoProfile -Command "$s=Read-Host -AsSecureString '  Clave SIIFA'; [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))"') do set "SIIFA_PASSWORD=%%P"
if not defined SIIFA_PASSWORD set /p "SIIFA_PASSWORD=  Clave SIIFA:   "
if not defined SIIFA_USER goto sincredenciales
if not defined SIIFA_PASSWORD goto sincredenciales
setx SIIFA_USER "%SIIFA_USER%" >nul
setx SIIFA_PASSWORD "%SIIFA_PASSWORD%" >nul
echo.
echo   [OK] Guardados. La proxima vez ya no los pide.
echo.

:carpeta
REM --- 4) Carpeta de trabajo (se valida ANTES de bajar nada) ----------
echo.
set "DEFCARP=D:\USUARIO CARTERA\Documents\SIIFA"
echo   Carpeta de trabajo de SIIFA (Enter para la de por defecto):
echo   [%DEFCARP%]
echo   Es una CARPETA, no un comando: algo como D:\...\SIIFA
set "CARPETA="
set /p "CARPETA=  Ruta: "
REM Primero la de por defecto y DESPUES quitar comillas: al reves, un Enter
REM (variable vacia) dejaba de carpeta la basura «"=» y todo fallaba luego.
if not defined CARPETA set "CARPETA=%DEFCARP%"
set "CARPETA=%CARPETA:"=%"
if not defined CARPETA goto carpetamala
:quitarbs
if "%CARPETA:~-1%"=="\" ( set "CARPETA=%CARPETA:~0,-1%" & goto quitarbs )
if not exist "%CARPETA%" mkdir "%CARPETA%" >nul 2>&1
if not exist "%CARPETA%" goto carpetamala
REM Que se pueda ESCRIBIR: de nada sirve bajar el informe y no poder guardarlo.
echo prueba> "%CARPETA%\_prueba_hus.tmp" 2>nul
if not exist "%CARPETA%\_prueba_hus.tmp" goto carpetasinpermiso
del "%CARPETA%\_prueba_hus.tmp" >nul 2>&1
echo   [OK] Carpeta lista: %CARPETA%

set "INFORME=%CARPETA%\informe_seguimientos.xlsx"
set "GLOSAS=%CARPETA%\respuestas_GLOSAS.xlsx"
set "DEVOL=%CARPETA%\respuestas_DEVOLUCIONES.xlsx"

:menu
REM Marcar lo que ya esta hecho: asi se ve de un vistazo por donde va.
set "HAYINF=falta"
set "HAYRES=faltan"
set "HAYPIL=falta"
if exist "%INFORME%" set "HAYINF=listo"
if exist "%GLOSAS%" set "HAYRES=listos"
if exist "%CARPETA%\piloto_siifa.csv" set "HAYPIL=hecho"
echo.
echo ============================================================
echo   Carpeta: %CARPETA%
echo ============================================================
echo   [1] Bajar de SIIFA el informe de seguimientos      (%HAYINF%)
echo   [2] Armar los archivos de respuestas               (%HAYRES%)
echo   [3] PILOTO - subir 1 sola glosa                    (%HAYPIL%)
echo   [4] Cargar TODAS las glosas
echo   [5] Cargar TODAS las devoluciones
echo   [6] Reintentar lo que quedo con error
echo   [7] Ver los codigos de respuesta que acepta SIIFA
echo   [8] Cambiar la carpeta de trabajo
echo   [0] Salir
echo.
set "OPCION="
set /p "OPCION=  Opcion: "
if "%OPCION%"=="1" goto informe
if "%OPCION%"=="2" goto armar
if "%OPCION%"=="3" goto piloto
if "%OPCION%"=="4" goto cargarglosas
if "%OPCION%"=="5" goto cargardevol
if "%OPCION%"=="6" goto reintentar
if "%OPCION%"=="7" goto catalogo
if "%OPCION%"=="8" goto carpeta
if "%OPCION%"=="0" goto fin
echo   [!] Escribe un numero del menu.
goto menu

:informe
echo.
echo --- Bajando de SIIFA todos los seguimientos (tarda varios minutos) ---
%PYEXE% tools\siifa_reporte_seguimientos.py --salida "%INFORME%"
goto hecho

:armar
echo.
echo   Export de tramites de DGH (el Excel grande, hoja BD TRAMITE).
echo   Es el que trae lo que el hospital YA respondio.
set "DGH="
set /p "DGH=  Ruta: "
REM Igual que con la carpeta: comprobar que escribio algo ANTES de tocarlo.
if not defined DGH goto sindgh
set "DGH=%DGH:"=%"
if not defined DGH goto sindgh
if not exist "%DGH%" goto sindgh
if not exist "%INFORME%" goto sininforme
echo.
echo --- Armando los archivos de respuestas ---
%PYEXE% tools\siifa_redactar_respuestas.py --informe "%INFORME%" --tramites "%DGH%" --salida-glosas "%GLOSAS%" --salida-devoluciones "%DEVOL%" --solo-lo-ya-respondido
echo.
echo   Los archivos _REDACTADAS son los que escribio el motor: NO se suben
echo   todavia, quedan para revisar y subir por tandas.
goto hecho

:piloto
if not exist "%GLOSAS%" goto singlosas
echo.
echo --- PILOTO: se sube UNA sola glosa, la primera del archivo ---
%PYEXE% tools\responder_glosas_siifa.py --excel "%GLOSAS%" --piloto 1 --reporte "%CARPETA%\piloto_siifa.csv"
echo.
echo   AHORA, ANTES DE SEGUIR: entra al portal, filtra esa factura,
echo   abre los tres puntos - Ver Historico y confirma que la respuesta
echo   quedo con SU codigo y SU fecha. Toma el pantallazo de evidencia.
goto hecho

:cargarglosas
if not exist "%GLOSAS%" goto singlosas
if not exist "%CARPETA%\piloto_siifa.csv" goto sinpiloto
echo.
echo --- Cargando TODAS las glosas ---
%PYEXE% tools\responder_glosas_siifa.py --excel "%GLOSAS%" --reporte "%CARPETA%\reporte_GLOSAS.csv" --saltar-csv "%CARPETA%\piloto_siifa.csv"
goto hecho

:cargardevol
if not exist "%DEVOL%" goto sindevol
echo.
echo --- Cargando TODAS las devoluciones ---
%PYEXE% tools\responder_glosas_siifa.py --excel "%DEVOL%" --reporte "%CARPETA%\reporte_DEVOLUCIONES.csv"
goto hecho

:reintentar
echo.
echo   [G] las glosas    [D] las devoluciones
set "CUAL="
set /p "CUAL=  Cual reintentar: "
if /i "%CUAL%"=="G" goto reintentarg
if /i "%CUAL%"=="D" goto reintentard
echo   [!] Escribe G o D.
goto menu

:reintentarg
if not exist "%CARPETA%\reporte_GLOSAS.csv" goto sinreporte
%PYEXE% tools\responder_glosas_siifa.py --excel "%GLOSAS%" --reporte "%CARPETA%\reporte_GLOSAS_2.csv" --saltar-csv "%CARPETA%\reporte_GLOSAS.csv"
goto hecho

:reintentard
if not exist "%CARPETA%\reporte_DEVOLUCIONES.csv" goto sinreporte
%PYEXE% tools\responder_glosas_siifa.py --excel "%DEVOL%" --reporte "%CARPETA%\reporte_DEVOLUCIONES_2.csv" --saltar-csv "%CARPETA%\reporte_DEVOLUCIONES.csv"
goto hecho

:catalogo
echo.
%PYEXE% tools\responder_glosas_siifa.py --listar-catalogo
goto hecho

:hecho
echo.
echo ------------------------------------------------------------
echo   Listo. Revisa los mensajes de arriba.
echo ------------------------------------------------------------
pause
goto menu

:sininforme
echo   [ERROR] Falta el informe de SIIFA. Corre primero la opcion [1].
pause
goto menu

:singlosas
echo   [ERROR] Falta %GLOSAS%. Corre primero la opcion [2].
pause
goto menu

:sindevol
echo   [ERROR] Falta %DEVOL%. Corre primero la opcion [2].
pause
goto menu

:sinpiloto
echo   [ERROR] Todavia no se ha hecho el piloto. Corre primero la [3]:
echo           es la regla del hospital, una sola glosa y se verifica.
pause
goto menu

:sinreporte
echo   [ERROR] No hay reporte de una corrida anterior que reintentar.
pause
goto menu

:sindgh
echo   [ERROR] No se encontro el export de DGH en esa ruta.
pause
goto menu

:carpetamala
echo.
echo   [ERROR] Esa ruta no sirve como carpeta:
echo           %CARPETA%
echo           Escribe SOLO la ruta de una carpeta (ej. D:\USUARIO CARTERA\Documents\SIIFA),
echo           sin comandos ni nombres de archivo. Enter usa la de por defecto.
echo.
goto carpeta

:carpetasinpermiso
echo.
echo   [ERROR] La carpeta existe pero no deja guardar archivos:
echo           %CARPETA%
echo           Elige otra (o revisa si la unidad de red esta conectada).
echo.
goto carpeta

:sincredenciales
echo   [ERROR] Sin usuario y clave no se puede entrar a SIIFA.
pause
exit /b 1

:fin
echo.
echo   Hasta luego.
echo.
exit /b 0

REM ==== Instalacion automatica de Python ==============================
:instalarpython
echo [i] No se encontro Python. Instalandolo automaticamente (sin admin),
echo     puede tardar unos minutos, NO cierres la ventana...
echo.
where winget >nul 2>&1 || goto py_descarga
winget install -e --id Python.Python.3.12 --silent --disable-interactivity --accept-package-agreements --accept-source-agreements >nul 2>&1
call :redetectar
if defined PYEXE goto pyok
:py_descarga
set "PYINST=%TEMP%\python_instalador_hus.exe"
set "PYURL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
del "%PYINST%" >nul 2>&1
echo [i] Descargando Python desde python.org - 25 MB aprox., espera...
curl.exe -L -s -o "%PYINST%" "%PYURL%" 2>nul
if not exist "%PYINST%" powershell -NoProfile -Command "Invoke-WebRequest -Uri $env:PYURL -OutFile $env:PYINST" >nul 2>&1
if not exist "%PYINST%" goto sinpython
"%PYINST%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%PYINST%" >nul 2>&1
call :redetectar
if defined PYEXE goto pyok
goto sinpython
:pyok
echo [OK] Python quedo instalado. Continuando...
echo.
goto deps
:redetectar
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if defined PYEXE goto :eof
python -c "import sys" >nul 2>&1 && set "PYEXE=python"
if defined PYEXE goto :eof
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set PYEXE="%%D\python.exe"
if defined PYEXE %PYEXE% -c "import sys" >nul 2>&1 || set "PYEXE="
goto :eof

:sinpython
echo [ERROR] No se pudo instalar Python. Instalalo de https://www.python.org/downloads/
echo         (marca "Add python.exe to PATH") y vuelve a intentar.
echo.
pause
exit /b 1
