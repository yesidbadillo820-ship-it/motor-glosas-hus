@echo off
REM ====================================================================
REM  EXCEL_A_CMD.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Por cada Excel (.xlsx, .xlsm, .xlsb, .xls) de la carpeta donde este
REM  ubicado este archivo (y sus subcarpetas) deja una copia identica
REM  con extension .cmd, lista para subir donde pidan ese formato:
REM      INFORME.xlsx  ->  INFORME.cmd
REM  El Excel original NUNCA se toca.
REM
REM  OJO: los .cmd generados NO son programas - son el mismo Excel con
REM  otra extension. No hay que darles doble clic; para abrirlos en
REM  Excel se renombran de vuelta a .xlsx.
REM
REM  USO:  copia este archivo a la carpeta que tiene tus Excel y dale
REM        doble clic.  Nada mas.
REM
REM  Es autocontenido: lleva el motor Python adentro. Si el equipo no
REM  tiene Python, el bot lo INSTALA SOLO (via winget o descargando el
REM  instalador oficial de python.org, sin pedir administrador). Solo
REM  necesita internet la primera vez. Si las politicas del equipo lo
REM  impiden, muestra las instrucciones para instalarlo a mano.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title EXCEL A CMD - Motor Glosas HUS

REM Carpeta donde vive este .cmd (sin la barra final, para no romper el "").
set "RAIZ=%~dp0"
if "%RAIZ:~-1%"=="\" set "RAIZ=%RAIZ:~0,-1%"

echo.
echo ============================================================
echo   EXCEL A CMD  -  deja cada Excel como archivo .cmd
echo ============================================================
echo   Carpeta de trabajo:
echo   "%RAIZ%"
echo.

REM --- 1) Buscar Python en el equipo ----------------------------------
REM  Se valida EJECUTANDO cada candidato (no con "where"): en Windows
REM  10/11 sin Python, "where python" encuentra el alias falso de la
REM  Microsoft Store y el bot moriria con codigo 9009 en vez de instalar.
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

:motor
REM --- 2) Localizar el motor Python -----------------------------------
REM  Preferimos el .py al lado (o en tools\); si el .cmd viaja solo,
REM  extraemos la copia embebida que va despues del marcador.
set "MOTOR=%~dp0excel_a_cmd.py"
if exist "%MOTOR%" goto run
set "MOTOR=%~dp0tools\excel_a_cmd.py"
if exist "%MOTOR%" goto run
set "MOTOR=%TEMP%\excel_a_cmd_hus.py"
set "ORIGENCMD=%~f0"
REM  Borrar cualquier motor viejo cacheado: si la extraccion fallara, NO
REM  se debe ejecutar en silencio una version anterior desde %TEMP%.
del "%MOTOR%" >nul 2>&1
REM  Las rutas viajan por variables de entorno ($env:...) y no interpoladas
REM  en el comando: asi un apostrofe o comilla en la ruta no rompe PowerShell.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:run
REM --- 3) Ejecutar la conversion ---------------------------------------
%PYEXE% "%MOTOR%" "%RAIZ%" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo [OK] Listo. Cada Excel quedo con su copia .cmd al lado, para subir. & echo      OJO: a los .cmd NO les des doble clic - son el Excel con otra extension. ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
echo.
pause
exit /b %RC%

REM ==== Instalacion automatica de Python ==============================
REM  Se intenta primero winget (viene con Windows 10/11) y si no,
REM  descargando el instalador oficial de python.org. Instalacion
REM  por-usuario: NO pide permisos de administrador.
:instalarpython
echo [i] No se encontro Python en este equipo.
echo [i] Instalando Python automaticamente - es gratis y no pide permisos
echo     de administrador. Puede tardar unos minutos, NO cierres esta
echo     ventana...
echo.

where winget >nul 2>&1 || goto py_descarga
echo [i] Instalando Python con winget...
winget install -e --id Python.Python.3.12 --silent --disable-interactivity --accept-package-agreements --accept-source-agreements >nul 2>&1
call :redetectar
if defined PYEXE goto pyok

:py_descarga
set "PYINST=%TEMP%\python_instalador_hus.exe"
set "PYURL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
del "%PYINST%" >nul 2>&1
echo [i] Descargando Python desde python.org - 25 MB aprox., espera...
curl.exe -L -s -o "%PYINST%" "%PYURL%" 2>nul
if exist "%PYINST%" goto py_instalar
powershell -NoProfile -Command "Invoke-WebRequest -Uri $env:PYURL -OutFile $env:PYINST" >nul 2>&1
if not exist "%PYINST%" goto sinpython

:py_instalar
echo [i] Instalando Python - solo para tu usuario, sin administrador...
"%PYINST%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%PYINST%" >nul 2>&1
call :redetectar
if defined PYEXE goto pyok
goto sinpython

:pyok
echo [OK] Python quedo instalado en este equipo. Continuando...
echo.
goto motor

REM  Vuelve a buscar Python despues de instalarlo. Se revisa tambien la
REM  carpeta tipica de la instalacion por-usuario, porque el PATH de la
REM  ventana actual no se refresca solo.
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
echo [ERROR] No se pudo instalar Python automaticamente en este equipo.
echo         Suele pasar cuando no hay internet o las politicas del
echo         equipo bloquean instalaciones.
echo.
echo   Para instalarlo a mano (gratis, 2 minutos):
echo     1^) Descargalo de:  https://www.python.org/downloads/
echo     2^) En el instalador MARCA la casilla "Add python.exe to PATH".
echo     3^) Vuelve a dar doble clic a este archivo.
echo.
echo   (Tambien sirve instalar "Python" desde la Microsoft Store, o
echo    pedirselo al area de SISTEMAS.)
echo.
pause
exit /b 1

:sinmotor
echo [ERROR] No se pudo preparar el motor de conversion.
echo         Copia tambien "excel_a_cmd.py" junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  A partir del marcador de la linea siguiente va el MOTOR en Python
REM  (copia embebida de tools\excel_a_cmd.py, salvo el fin de linea).
REM  cmd.exe NUNCA llega aqui: el script termina con "exit /b" mas
REM  arriba. Esta copia solo se usa si el .cmd viaja solo, sin el .py
REM  al lado.
REM ====================================================================
#PYSTART#
"""excel_a_cmd.py — Deja cada Excel de las carpetas como archivo .cmd.

Para el flujo de auditoría que exige subir archivos con extensión .cmd:
recorre una carpeta raíz y, por CADA Excel que encuentre (.xlsx, .xlsm,
.xlsb, .xls), deja al lado una copia idéntica con extensión .cmd:

    INFORME.xlsx  →  INFORME.cmd   (mismo contenido byte a byte)

El Excel original NUNCA se toca. La copia .cmd NO es ejecutable ni hay que
darle doble clic — quien la reciba la renombra de vuelta a .xlsx (o la
extensión original) y la abre en Excel normalmente.

Es idempotente: si la copia .cmd ya existe se refresca en cada corrida,
para que nunca quede una versión vieja del Excel. Seguridad: si en el
destino ya existe un .cmd con ese nombre que NO es un Excel (por ejemplo un
script real, o este mismo bot), se salta con un aviso — jamás lo pisa. Los
temporales de Office (``~$...``) se ignoran.

USO:
    py tools\\excel_a_cmd.py "D:\\USUARIO CARTERA\\Documents\\SOPORTES"
    py tools\\excel_a_cmd.py .                    # carpeta actual
    py tools\\excel_a_cmd.py . --simulacro        # solo mostrar, sin escribir
    py tools\\excel_a_cmd.py . --sin-recursion    # solo la carpeta raíz

Normalmente NO se ejecuta a mano: el archivo `EXCEL_A_CMD.cmd` lo lanza con
doble clic sobre la carpeta donde esté ubicado. No requiere instalar ningún
componente extra (solo Python; el lanzador lo instala si falta).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import sys
from pathlib import Path

EXTENSIONES = (".xlsx", ".xlsm", ".xlsb", ".xls")

# Firmas de archivo: ZIP (xlsx/xlsm/xlsb) y OLE2 (xls clásico).
_FIRMA_ZIP = b"PK\x03\x04"
_FIRMA_OLE = b"\xd0\xcf\x11\xe0"


def clave_natural(nombre: str) -> list:
    """Orden natural: 'a2' antes que 'a10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nombre)]


def es_contenido_excel(ruta: Path) -> bool:
    """True si los primeros bytes corresponden a un archivo de Excel."""
    try:
        with open(ruta, "rb") as fh:
            inicio = fh.read(4)
    except OSError:
        return False
    return inicio.startswith(_FIRMA_ZIP) or inicio.startswith(_FIRMA_OLE)


def listar_excels(carpeta: Path) -> list[Path]:
    """Excels sueltos en `carpeta` (no recursivo), sin temporales de Office."""
    excels = []
    for entrada in os.scandir(carpeta):
        if not entrada.is_file():
            continue
        nombre = entrada.name
        if nombre.startswith("~$"):
            continue  # archivo de bloqueo temporal de Office
        if nombre.lower().endswith(EXTENSIONES):
            excels.append(Path(entrada.path))
    return sorted(excels, key=lambda p: clave_natural(p.name))


def copiar_como(origen: Path, destino: Path) -> None:
    """Copia byte a byte con escritura atómica."""
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    try:
        shutil.copyfile(origen, tmp)
        os.replace(tmp, destino)
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def procesar(raiz: Path, recursivo: bool, simulacro: bool) -> int:
    carpetas = [Path(dp) for dp, _dn, _fn in os.walk(raiz)] if recursivo else [raiz]
    carpetas.sort(key=lambda p: clave_natural(str(p)))

    convertidos = 0
    saltados: list[str] = []
    con_error: list[str] = []

    print("=" * 64)
    print("  EXCEL A CMD — una copia .cmd por cada Excel")
    print("=" * 64)
    print(f"  Raíz: {raiz}")
    print(
        f"  Modo: {'SIMULACRO (no escribe nada)' if simulacro else 'real'}"
        f" | {'con subcarpetas' if recursivo else 'solo la raíz'}"
    )
    print("-" * 64)

    for carpeta in carpetas:
        excels = listar_excels(carpeta)
        if not excels:
            continue
        rel = carpeta.name if carpeta != raiz else "(carpeta raíz)"
        destinos_vistos: set[str] = set()
        for excel in excels:
            destino = excel.with_suffix(".cmd")
            # Dos Excels distintos que producirían el mismo .cmd
            # (p. ej. INFORME.xlsx e INFORME.xls en la misma carpeta).
            if destino.name.lower() in destinos_vistos:
                saltados.append(f"{excel.name} (chocaría con otro {destino.name})")
                print(f"  ·  {rel}: {excel.name} se omite — ya se generó {destino.name}")
                continue
            destinos_vistos.add(destino.name.lower())
            # Jamás pisar un .cmd que no sea un Excel (un script real, este bot…).
            if destino.exists() and not es_contenido_excel(destino):
                saltados.append(f"{excel.name} (ya existe {destino.name} y no es un Excel)")
                print(f"  ·  {rel}: {excel.name} se omite — {destino.name} no es un Excel")
                continue

            if simulacro:
                print(f"  →  {rel}: {excel.name}  →  {destino.name}")
                convertidos += 1
                continue
            try:
                copiar_como(excel, destino)
                convertidos += 1
                print(f"  ✓  {rel}: {excel.name}  →  {destino.name}")
            except Exception as exc:  # archivo bloqueado/solo-lectura: seguir
                con_error.append(f"{excel.name} ({type(exc).__name__})")
                print(f"  ✗  {rel}: {excel.name} falló ({type(exc).__name__}), se sigue")

    print("-" * 64)
    verbo = "se convertirían" if simulacro else "convertidos"
    print(f"  Resumen: {convertidos} Excel {verbo} a .cmd.")
    if convertidos and not simulacro:
        print("           Los Excel originales quedaron intactos.")
        print("           OJO: a los .cmd generados NO les des doble clic — no son programas.")
        print("           Para abrir uno en Excel, renómbralo de vuelta a .xlsx.")
    if saltados:
        print(f"           {len(saltados)} archivo(s) omitidos por seguridad (ver arriba).")
    if con_error:
        print(f"           {len(con_error)} archivo(s) con error: {', '.join(con_error)}")
    if convertidos == 0 and not saltados:
        print("           No se encontraron archivos de Excel en esta carpeta ni en")
        print("           sus subcarpetas (busca .xlsx, .xlsm, .xlsb y .xls).")
    print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deja cada Excel de las carpetas como archivo .cmd (copia idéntica).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "raiz", nargs="?", default=".", help="Carpeta a procesar (por defecto, la actual)."
    )
    parser.add_argument(
        "--sin-recursion",
        action="store_true",
        help="Procesar solo la carpeta raíz, sin subcarpetas.",
    )
    parser.add_argument(
        "--simulacro",
        "--dry-run",
        action="store_true",
        help="Mostrar qué haría, sin escribir ningún archivo.",
    )
    args = parser.parse_args(argv)

    raiz = Path(args.raiz).expanduser().resolve()
    if not raiz.is_dir():
        sys.stderr.write(f"ERROR: no existe la carpeta: {raiz}\n")
        return 2

    return procesar(raiz=raiz, recursivo=not args.sin_recursion, simulacro=args.simulacro)


if __name__ == "__main__":
    raise SystemExit(main())
