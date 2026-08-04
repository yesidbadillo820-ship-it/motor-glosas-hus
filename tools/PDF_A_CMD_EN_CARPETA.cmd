@echo off
REM ====================================================================
REM  PDF_A_CMD_EN_CARPETA.cmd  -  Bot de doble clic del Motor Glosas HUS.
REM  Busca TODOS los PDF de la carpeta donde este este archivo (y sus
REM  subcarpetas), convierte cada uno a .cmd (copia identica, sin unir)
REM  y deja TODAS las copias JUNTAS dentro de una carpeta nueva:
REM
REM      CMD_CONVERTIDOS\FACTURA.cmd
REM      CMD_CONVERTIDOS\EPICRISIS.cmd  ...
REM
REM  - Los PDF originales NUNCA se tocan ni se mueven.
REM  - Si dos PDF de carpetas distintas se llaman igual, la copia lleva
REM    el nombre de su carpeta adelante para no pisarse.
REM  - Correrlo otra vez REFRESCA las copias (idempotente).
REM  (Su hermano PDF_A_CMD.cmd deja cada copia AL LADO del PDF;
REM   este las junta todas en una sola carpeta lista para subir.)
REM
REM  OJO: los .cmd generados NO son programas - son el mismo PDF con
REM  otra extension. No hay que darles doble clic; para verlos como
REM  documento se renombran de vuelta a .pdf.
REM
REM  USO:  copia este archivo a la carpeta que tiene tus PDF y dale
REM        doble clic.  Nada mas.
REM
REM  Es autocontenido: lleva el motor Python adentro. Si el equipo no
REM  tiene Python, el bot lo INSTALA SOLO (via winget o descargando el
REM  instalador oficial de python.org, sin pedir administrador).
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title PDF A CMD EN CARPETA - Motor Glosas HUS

REM Carpeta donde vive este .cmd (sin la barra final, para no romper el "").
set "RAIZ=%~dp0"
if "%RAIZ:~-1%"=="\" set "RAIZ=%RAIZ:~0,-1%"

echo.
echo ============================================================
echo   PDF A CMD EN CARPETA - junta todos los .cmd en una carpeta
echo ============================================================
echo   Carpeta de trabajo:
echo   "%RAIZ%"
echo   Las copias quedaran en:  "%RAIZ%\CMD_CONVERTIDOS"
echo.

REM --- 1) Buscar Python en el equipo ----------------------------------
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( python -c "import sys" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( python3 -c "import sys" >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto instalarpython

:motor
REM --- 2) Localizar el motor Python -----------------------------------
set "MOTOR=%~dp0pdf_a_cmd_en_carpeta.py"
if exist "%MOTOR%" goto run
set "MOTOR=%~dp0tools\pdf_a_cmd_en_carpeta.py"
if exist "%MOTOR%" goto run
set "MOTOR=%TEMP%\pdf_a_cmd_en_carpeta_hus.py"
set "ORIGENCMD=%~f0"
del "%MOTOR%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath $env:ORIGENCMD -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath $env:MOTOR -Encoding UTF8"
if errorlevel 1 goto sinmotor
if not exist "%MOTOR%" goto sinmotor

:run
REM --- 3) Ejecutar la conversion ---------------------------------------
%PYEXE% "%MOTOR%" "%RAIZ%" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo [OK] Listo. Todos los .cmd quedaron JUNTOS en la carpeta CMD_CONVERTIDOS. & echo      OJO: a los .cmd NO les des doble clic - son el PDF con otra extension. ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
echo.
pause
exit /b %RC%

REM ==== Instalacion automatica de Python ==============================
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
pause
exit /b 1

:sinmotor
echo [ERROR] No se pudo preparar el motor de conversion.
echo         Copia tambien "pdf_a_cmd_en_carpeta.py" junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  A partir del marcador de la linea siguiente va el MOTOR en Python.
REM  cmd.exe NUNCA llega aqui: el script termina con "exit /b" mas arriba.
REM ====================================================================
#PYSTART#
"""pdf_a_cmd_en_carpeta.py — Junta en UNA carpeta la copia .cmd de cada PDF.

Variante de pdf_a_cmd.py: recorre la carpeta raíz y sus subcarpetas, y por
CADA PDF deja una copia idéntica con extensión .cmd — pero en vez de dejarla
al lado del original, TODAS las copias quedan juntas en una carpeta nueva:

    <raíz>\\CMD_CONVERTIDOS\\FACTURA.cmd
    <raíz>\\CMD_CONVERTIDOS\\EPICRISIS.cmd ...

- Los PDF originales NUNCA se tocan ni se mueven.
- Colisiones de nombre (dos PDF iguales en carpetas distintas): la copia
  lleva el nombre de su carpeta adelante (CARPETA_FACTURA.cmd) y, si aun
  así choca, un número (_2, _3…). Nada se pisa en silencio.
- Idempotente: correrlo otra vez refresca las copias.
- Seguridad: jamás pisa un .cmd que no sea un PDF por dentro.

USO:
    py tools\\pdf_a_cmd_en_carpeta.py "D:\\SOPORTES"
    py tools\\pdf_a_cmd_en_carpeta.py . --simulacro     # solo mostrar
    py tools\\pdf_a_cmd_en_carpeta.py . --sin-recursion # solo la raíz
    py tools\\pdf_a_cmd_en_carpeta.py . --destino OTRA_CARPETA

Normalmente NO se ejecuta a mano: el archivo `PDF_A_CMD_EN_CARPETA.cmd`
lo lanza con doble clic sobre la carpeta donde esté ubicado.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import sys
from pathlib import Path

NOMBRE_DESTINO = "CMD_CONVERTIDOS"


def clave_natural(nombre: str) -> list:
    """Orden natural: 'a2' antes que 'a10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nombre)]


def es_contenido_pdf(ruta: Path) -> bool:
    """True si el archivo es un PDF (la firma %PDF- va en los primeros bytes)."""
    try:
        with open(ruta, "rb") as fh:
            inicio = fh.read(1024)
    except OSError:
        return False
    return b"%PDF-" in inicio


def listar_pdfs(carpeta: Path) -> list[Path]:
    """PDFs sueltos en `carpeta` (no recursivo)."""
    pdfs = []
    try:
        for entrada in os.scandir(carpeta):
            if entrada.is_file() and entrada.name.lower().endswith(".pdf"):
                pdfs.append(Path(entrada.path))
    except OSError:
        return []
    return sorted(pdfs, key=lambda p: clave_natural(p.name))


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


def nombre_libre(usados: dict, pdf: Path, carpeta: Path, raiz: Path) -> str:
    """Nombre de la copia dentro del destino, resolviendo colisiones."""
    base = pdf.stem + ".cmd"
    if base.lower() not in usados:
        return base
    # Colisión: anteponer la carpeta del PDF (si no es la raíz)
    if carpeta != raiz:
        con_carpeta = f"{carpeta.name}_{base}"
        if con_carpeta.lower() not in usados:
            return con_carpeta
        base = con_carpeta
    n = 2
    while True:
        candidato = f"{Path(base).stem}_{n}.cmd"
        if candidato.lower() not in usados:
            return candidato
        n += 1


def procesar(raiz: Path, recursivo: bool, simulacro: bool, nombre_destino: str) -> int:
    destino_dir = (raiz / nombre_destino).resolve()

    if recursivo:
        carpetas = []
        for dp, dn, _fn in os.walk(raiz):
            # Nunca entrar a la carpeta de destino (ni reconvertir lo ya copiado)
            dn[:] = [d for d in dn if (Path(dp) / d).resolve() != destino_dir]
            carpetas.append(Path(dp))
    else:
        carpetas = [raiz]
    carpetas.sort(key=lambda p: clave_natural(str(p)))

    convertidos = 0
    saltados: list[str] = []
    con_error: list[str] = []
    usados: dict[str, Path] = {}

    print("=" * 64)
    print("  PDF A CMD EN CARPETA — todas las copias .cmd juntas")
    print("=" * 64)
    print(f"  Raíz:    {raiz}")
    print(f"  Destino: {destino_dir}")
    print(
        f"  Modo: {'SIMULACRO (no escribe nada)' if simulacro else 'real'}"
        f" | {'con subcarpetas' if recursivo else 'solo la raíz'}"
    )
    print("-" * 64)

    if not simulacro:
        destino_dir.mkdir(parents=True, exist_ok=True)

    for carpeta in carpetas:
        pdfs = listar_pdfs(carpeta)
        if not pdfs:
            continue
        rel = carpeta.name if carpeta != raiz else "(carpeta raíz)"
        for pdf in pdfs:
            nombre = nombre_libre(usados, pdf, carpeta, raiz)
            destino = destino_dir / nombre
            # Jamás pisar un .cmd que no sea un PDF por dentro.
            if destino.exists() and not es_contenido_pdf(destino):
                saltados.append(f"{pdf.name} (ya existe {nombre} y no es un PDF)")
                print(f"  ·  {rel}: {pdf.name} se omite — {nombre} no es un PDF")
                continue

            usados[nombre.lower()] = pdf
            if simulacro:
                print(f"  →  {rel}: {pdf.name}  →  {nombre_destino}\\{nombre}")
                convertidos += 1
                continue
            try:
                copiar_como(pdf, destino)
                convertidos += 1
                print(f"  ✓  {rel}: {pdf.name}  →  {nombre_destino}\\{nombre}")
            except Exception as exc:  # archivo bloqueado/solo-lectura: seguir
                con_error.append(f"{pdf.name} ({type(exc).__name__})")
                print(f"  ✗  {rel}: {pdf.name} falló ({type(exc).__name__}), se sigue")

    print("-" * 64)
    verbo = "se copiarían" if simulacro else "copiados"
    print(f"  Resumen: {convertidos} PDF {verbo} como .cmd DENTRO de {nombre_destino}\\")
    if convertidos and not simulacro:
        print("           Los PDF originales quedaron intactos en sus carpetas.")
        print("           OJO: a los .cmd NO les des doble clic — no son programas.")
        print("           Para ver uno como documento, renómbralo de vuelta a .pdf.")
    if saltados:
        print(f"           {len(saltados)} archivo(s) omitidos por seguridad (ver arriba).")
    if con_error:
        print(f"           {len(con_error)} archivo(s) con error: {', '.join(con_error)}")
    if convertidos == 0 and not saltados:
        print("           No se encontraron PDF en esta carpeta ni en sus subcarpetas.")
    print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convierte cada PDF a .cmd y junta TODAS las copias en una carpeta nueva.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "raiz", nargs="?", default=".", help="Carpeta a procesar (por defecto, la actual)."
    )
    parser.add_argument(
        "--destino",
        default=NOMBRE_DESTINO,
        help=f"Nombre de la carpeta donde quedan las copias (por defecto {NOMBRE_DESTINO}).",
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

    return procesar(
        raiz=raiz,
        recursivo=not args.sin_recursion,
        simulacro=args.simulacro,
        nombre_destino=args.destino,
    )


if __name__ == "__main__":
    raise SystemExit(main())
