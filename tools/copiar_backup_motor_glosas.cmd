@echo off
rem ================================================================
rem  COPIA DE SEGURIDAD diaria del Motor de Glosas hacia otra carpeta
rem  (share del hospital o carpeta sincronizada con Drive/OneDrive),
rem  para que la base y su copia NO vivan en el mismo disco.
rem  La tarea programada la crea MONTAR_SERVIDOR_MOTOR_GLOSAS.cmd y
rem  corre a diario a las 9:00 a.m. El destino queda guardado en
rem  data\destino_backup.txt (se puede editar con el Bloc de notas).
rem ================================================================
setlocal
set "REPO=C:\motor-glosas\repo"
set "LOG=%REPO%\data\autodeploy.log"
if not exist "%REPO%\data\destino_backup.txt" (
  echo [%date% %time%] BACKUP: falta data\destino_backup.txt con la carpeta destino >> "%LOG%"
  exit /b 0
)
set /p DESTINO=<"%REPO%\data\destino_backup.txt"
if not exist "%DESTINO%" mkdir "%DESTINO%" >nul 2>&1
if not exist "%DESTINO%" (
  echo [%date% %time%] BACKUP: no se pudo acceder al destino %DESTINO% >> "%LOG%"
  exit /b 0
)

rem La copia mas reciente que dejo el mantenimiento interno de las 3 a.m.
set "ULTIMO="
for /f "delims=" %%f in ('dir /b /o-d "%REPO%\data\backups\*.db" 2^>nul') do (
  if not defined ULTIMO set "ULTIMO=%%f"
)
if not defined ULTIMO (
  echo [%date% %time%] BACKUP: aun no hay copias en data\backups >> "%LOG%"
  exit /b 0
)
copy /y "%REPO%\data\backups\%ULTIMO%" "%DESTINO%\" >nul
if errorlevel 1 (
  echo [%date% %time%] BACKUP: fallo copiando %ULTIMO% a %DESTINO% >> "%LOG%"
) else (
  echo [%date% %time%] BACKUP: %ULTIMO% copiado a %DESTINO% >> "%LOG%"
)
exit /b 0
