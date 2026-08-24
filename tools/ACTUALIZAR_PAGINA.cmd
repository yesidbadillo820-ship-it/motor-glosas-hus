@echo off
REM ====================================================================
REM  ACTUALIZAR_PAGINA.cmd  -  Trae los cambios nuevos y los deja
REM  funcionando en la pagina, ahora mismo, sin esperar los 5 minutos
REM  del autodespliegue.
REM
REM  POR QUE EXISTE (24-08-2026). El autodespliegue automatico corre
REM  cada 5 minutos, pero usa un candado para no pisarse consigo mismo.
REM  Si una pasada se queda colgada -por ejemplo, GitHub no contesta-
REM  el candado no se suelta y TODAS las pasadas siguientes se saltan:
REM  el PC se queda con la version vieja y en pantalla no se ve nada
REM  raro. Paso ese mismo dia: el hospital estuvo horas atrasado.
REM
REM  Este bot hace lo mismo que el automatico pero A LA VISTA: dice que
REM  version hay, que cambios entran, aplica, reinicia el motor y
REM  comprueba que la pagina volvio a responder. Y de paso suelta el
REM  candado si quedo trabado, para que el automatico vuelva a andar.
REM
REM  USO: doble clic. Al terminar, en el navegador: Ctrl + F5.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions
title MOTOR GLOSAS HUS - Actualizar la pagina

cd /d "%~dp0.."
set "REPO=%CD%"
set "LOG=%REPO%\data\autodeploy.log"
set "CANDADO=%REPO%\data\autodeploy.lock"
REM  Git NUNCA debe quedarse esperando que alguien escriba usuario y
REM  clave: aqui no hay nadie mirando esa ventana.
set "GIT_TERMINAL_PROMPT=0"

echo.
echo  ============================================================
echo    ACTUALIZAR LA PAGINA DEL MOTOR DE GLOSAS
echo  ============================================================
echo.
echo  Carpeta: %REPO%
echo.

REM --- Git tiene que existir ------------------------------------------
where git >nul 2>&1 && goto :hay_git
if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "PATH=%PATH%;%ProgramFiles(x86)%\Git\cmd"
if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Git\cmd"
where git >nul 2>&1 && goto :hay_git
echo  [X] No se encuentra Git en este PC. Sin Git no se puede actualizar.
echo      Instalelo desde https://git-scm.com/download/win y vuelva a intentar.
goto :final
:hay_git

REM --- Candado trabado del autodespliegue -----------------------------
if not exist "%CANDADO%" goto :sin_candado
set "EDAD=999"
for /f "usebackq delims=" %%E in (`powershell -NoProfile -Command "try{$t=(Get-Item '%CANDADO%').LastWriteTime; [int]((Get-Date)-$t).TotalMinutes}catch{999}"`) do set "EDAD=%%E"
if "%EDAD%"=="" set "EDAD=999"
if %EDAD% GEQ 10 (
  echo  [!] El autodespliegue tenia un candado de %EDAD% minutos sin soltar:
  echo      se libera para que vuelva a funcionar solo.
  del "%CANDADO%" >nul 2>&1
  echo [%date% %time%] candado de %EDAD% min liberado a mano desde ACTUALIZAR_PAGINA >> "%LOG%"
) else (
  echo  [!] El autodespliegue esta trabajando en este momento ^(%EDAD% min^).
  echo      Espere un minuto y vuelva a abrir este bot.
  goto :final
)
:sin_candado

echo  [1/5] Version que tiene el PC ahora:
git log --oneline -1
echo.

echo  [2/5] Preguntando a GitHub si hay algo nuevo...
REM  Con tope de tiempo: si GitHub no contesta, se corta y se avisa, en
REM  vez de dejar la ventana colgada para siempre.
powershell -NoProfile -Command "$p=Start-Process -FilePath 'git' -ArgumentList 'fetch','origin','motor-glosas' -WorkingDirectory '%REPO%' -PassThru -WindowStyle Hidden; if(-not $p.WaitForExit(180000)){ try{ $p.Kill() }catch{}; exit 1 }; exit $p.ExitCode"
if errorlevel 1 (
  echo  [X] No se pudo consultar GitHub ^(sin internet, o tardo demasiado^).
  echo      El PC se queda con la version que tiene. Intente mas tarde.
  goto :final
)

for /f %%a in ('git rev-parse HEAD') do set "LOCAL=%%a"
for /f %%a in ('git rev-parse origin/motor-glosas') do set "REMOTO=%%a"
if "%LOCAL%"=="%REMOTO%" (
  echo.
  echo  [OK] La pagina YA ESTA AL DIA: no hay nada nuevo que bajar.
  echo       Si aun ve la pantalla vieja, es el navegador: Ctrl + F5.
  goto :final
)

echo.
echo  [3/5] Cambios que van a entrar:
git log --oneline HEAD..origin/motor-glosas
echo.

git reset --hard origin/motor-glosas
if errorlevel 1 (
  echo  [X] No se pudo aplicar el codigo nuevo. Avise antes de seguir.
  goto :final
)
echo [%date% %time%] actualizado a mano desde ACTUALIZAR_PAGINA: %REMOTO:~0,7% >> "%LOG%"

echo  [4/5] Revisando programas que necesita el motor...
REM  psycopg2 es solo para PostgreSQL: aca la base es SQLite, se salta.
findstr /v /i "psycopg2" "%REPO%\requirements.txt" > "%REPO%\data\requirements_local.txt"
"%REPO%\venv\Scripts\python.exe" -m pip install -r "%REPO%\data\requirements_local.txt" -q

echo  [5/5] Reiniciando el motor de la pagina ^(puerto 8080^)...
REM  Se le pide que se cierre y solo si no hace caso en 8 segundos se
REM  fuerza: asi lo que estuviera contestando alcanza a terminar.
powershell -NoProfile -Command "$ps=Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object {$_.CommandLine -match 'uvicorn app.main:app' -and $_.CommandLine -match '--port\s+8080'}; foreach($p in $ps){ Stop-Process -Id $p.ProcessId -ErrorAction SilentlyContinue }; Start-Sleep -Seconds 8; foreach($p in $ps){ if(Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue){ Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } }"

REM  El vigilante lo revive; se le da tiempo preguntando cada 3 segundos.
set /a INTENTOS=0
:esperar
powershell -NoProfile -Command "try{ $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8080/health' -TimeoutSec 5 -UseBasicParsing; exit 0 }catch{ exit 1 }"
if not errorlevel 1 goto :arriba
set /a INTENTOS+=1
if %INTENTOS% GEQ 30 goto :no_subio
ping -n 4 127.0.0.1 >nul
goto :esperar

:no_subio
echo.
echo  [!] El motor no volvio solo. Se arranca directo...
start "MotorGlosas" /min cmd /s /c ""%REPO%\venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8080 >> "%REPO%\data\servidor.log" 2>&1"
ping -n 16 127.0.0.1 >nul
powershell -NoProfile -Command "try{ $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8080/health' -TimeoutSec 5 -UseBasicParsing; exit 0 }catch{ exit 1 }"
if errorlevel 1 (
  echo  [X] LA PAGINA SIGUE CAIDA. Abra ESTADO_MOTOR.cmd y avise.
  goto :final
)

:arriba
echo.
echo  ============================================================
echo    LISTO. La pagina ya esta con la version nueva:
echo  ============================================================
git log --oneline -1
echo.
echo  AHORA, EN CADA COMPUTADOR QUE USE LA PAGINA:
echo    presione  Ctrl + F5  para que el navegador suelte la copia vieja.
echo.

:final
echo.
pause
