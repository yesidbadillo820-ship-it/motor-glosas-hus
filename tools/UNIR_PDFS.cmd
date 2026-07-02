@echo off
REM ====================================================================
REM  UNIR_PDFS.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Une (combina) todos los PDF de cada carpeta en un unico PDF
REM  consolidado (_UNIDO_<carpeta>.pdf).  Trabaja sobre la carpeta donde
REM  este ubicado este archivo y todas sus subcarpetas.
REM
REM  USO:  copia este archivo a la carpeta que tiene tus PDF y dale
REM        doble clic.  Nada mas.
REM
REM  Es autocontenido: lleva el motor Python adentro. Solo necesita que
REM  Python este instalado en el equipo (https://www.python.org/downloads/).
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title UNIR PDFS - Motor Glosas HUS

REM Carpeta donde vive este .cmd (sin la barra final, para no romper el "").
set "RAIZ=%~dp0"
if "%RAIZ:~-1%"=="\" set "RAIZ=%RAIZ:~0,-1%"

echo.
echo ============================================================
echo   UNIR PDFS  -  une los PDF de cada carpeta en un solo PDF
echo ============================================================
echo   Carpeta de trabajo:
echo   %RAIZ%
echo.

REM --- 1) Buscar Python en el equipo ----------------------------------
set "PYEXE="
where py      >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE ( where python  >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE ( where python3 >nul 2>&1 && set "PYEXE=python3" )
if not defined PYEXE goto sinpython

REM --- 2) Asegurar el componente PDF (PyPDF2 / pypdf) -----------------
%PYEXE% -c "import PyPDF2" >nul 2>&1 && goto haspdf
%PYEXE% -c "import pypdf"  >nul 2>&1 && goto haspdf
echo [i] Instalando el componente PDF (PyPDF2) por unica vez, espera...
%PYEXE% -m pip install --quiet --user PyPDF2 >nul 2>&1
:haspdf

REM --- 3) Localizar el motor Python -----------------------------------
REM  Preferimos el .py al lado (o en tools\); si el .cmd viaja solo,
REM  extraemos la copia embebida que va despues del marcador.
set "MOTOR=%~dp0unir_pdfs_carpetas.py"
if exist "%MOTOR%" goto run
set "MOTOR=%~dp0tools\unir_pdfs_carpetas.py"
if exist "%MOTOR%" goto run
set "MOTOR=%TEMP%\unir_pdfs_carpetas_hus.py"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l=Get-Content -LiteralPath '%~f0' -Encoding UTF8; $h=$l|Select-String -SimpleMatch ('#PY'+'START#'); if(-not $h){exit 3}; $k=$h[0].LineNumber; ($l[$k..($l.Count-1)]) -join [Environment]::NewLine | Set-Content -LiteralPath '%MOTOR%' -Encoding UTF8"
if not exist "%MOTOR%" goto sinmotor

:run
REM --- 4) Ejecutar la union -------------------------------------------
%PYEXE% "%MOTOR%" "%RAIZ%" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo [OK] Listo. Revisa los archivos _UNIDO_*.pdf dentro de cada carpeta. ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
echo.
pause
exit /b %RC%

:sinpython
echo [ERROR] No se encontro Python en este equipo.
echo.
echo   Este bot necesita Python (gratis) para poder unir los PDF:
echo     1^) Descargalo de:  https://www.python.org/downloads/
echo     2^) En el instalador MARCA la casilla "Add python.exe to PATH".
echo     3^) Vuelve a dar doble clic a este archivo.
echo.
pause
exit /b 1

:sinmotor
echo [ERROR] No se pudo preparar el motor de union.
echo         Copia tambien "unir_pdfs_carpetas.py" junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  A partir del marcador de la linea siguiente va el MOTOR en Python
REM  (copia embebida de tools\unir_pdfs_carpetas.py, salvo el fin de
REM  linea). cmd.exe NUNCA llega aqui: el script termina con "exit /b"
REM  mas arriba. Esta copia solo se usa si el .cmd viaja solo, sin el
REM  .py al lado.
REM ====================================================================
#PYSTART#
"""unir_pdfs_carpetas.py — Une (combina) todos los PDF de cada carpeta en uno solo.

Pensado para consolidar los soportes de glosas/notas de crédito: cada carpeta
(por factura / NE) suele tener varios PDF sueltos (factura, epicrisis, notas,
autorizaciones…). Este script recorre una carpeta raíz y, para CADA carpeta que
contenga varios PDF, los une en un único PDF consolidado llamado
`_UNIDO_<nombre-de-la-carpeta>.pdf` dentro de esa misma carpeta.

Es idempotente: en cada corrida vuelve a generar los `_UNIDO_*.pdf` y NUNCA los
toma como entrada (se excluyen por el prefijo), así que puedes correrlo las veces
que quieras sin que se aniden.

Orden de las páginas: los PDF de cada carpeta se ordenan por nombre de archivo
de forma "natural" (2 antes que 10). Si necesitas un orden exacto, antepón un
número al nombre: `01_factura.pdf`, `02_epicrisis.pdf`, `03_autorizacion.pdf`.

USO:
    py tools\\unir_pdfs_carpetas.py "D:\\USUARIO CARTERA\\Documents\\SOPORTES"
    py tools\\unir_pdfs_carpetas.py .                      # carpeta actual
    py tools\\unir_pdfs_carpetas.py . --simulacro          # solo mostrar, sin escribir
    py tools\\unir_pdfs_carpetas.py . --minimo 1           # unir aunque haya 1 solo PDF
    py tools\\unir_pdfs_carpetas.py . --sin-recursion      # solo la carpeta raíz

Normalmente NO se ejecuta a mano: el archivo `UNIR_PDFS.cmd` lo lanza con doble
clic sobre la carpeta donde esté ubicado.

Requiere PyPDF2 (o pypdf). El repo ya fija PyPDF2==3.0.1.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
from pathlib import Path


def _cargar_lector_escritor():
    """Devuelve (PdfReader, PdfWriter) desde pypdf o PyPDF2, lo que haya."""
    try:
        from pypdf import PdfReader, PdfWriter

        return PdfReader, PdfWriter
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader, PdfWriter

        return PdfReader, PdfWriter
    except ImportError:
        sys.stderr.write(
            "\nERROR: falta el componente para leer PDF (PyPDF2 / pypdf).\n"
            "       Instálalo con:  py -m pip install PyPDF2\n\n"
        )
        sys.exit(2)


def clave_natural(nombre: str) -> list:
    """Orden natural: 'a2' antes que 'a10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nombre)]


def listar_pdfs(carpeta: Path, prefijo: str) -> list[Path]:
    """PDF sueltos en `carpeta` (no recursivo), excluyendo los ya unidos."""
    pref = prefijo.upper()
    pdfs = []
    for entrada in os.scandir(carpeta):
        if not entrada.is_file():
            continue
        nombre = entrada.name
        if not nombre.lower().endswith(".pdf"):
            continue
        if nombre.upper().startswith(pref):
            continue  # es un _UNIDO_ de una corrida previa
        pdfs.append(Path(entrada.path))
    return sorted(pdfs, key=lambda p: clave_natural(p.name))


def unir_pdfs(pdfs: list[Path], destino: Path, PdfReader, PdfWriter) -> tuple[int, list[str]]:
    """Une `pdfs` en `destino`. Devuelve (n_paginas, [archivos_omitidos])."""
    escritor = PdfWriter()
    paginas = 0
    omitidos: list[str] = []
    for pdf in pdfs:
        try:
            lector = PdfReader(str(pdf))
            if lector.is_encrypted:
                # PDFs "protegidos" sin contraseña real: se intenta abrir vacío.
                with contextlib.suppress(Exception):
                    lector.decrypt("")
            n = 0
            for pagina in lector.pages:
                escritor.add_page(pagina)
                n += 1
            if n == 0:
                omitidos.append(f"{pdf.name} (sin páginas legibles)")
            else:
                paginas += n
        except Exception as exc:  # PDF dañado/ilegible: se omite y se sigue
            omitidos.append(f"{pdf.name} ({type(exc).__name__})")
    if paginas == 0:
        return 0, omitidos
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        escritor.write(fh)
    os.replace(tmp, destino)  # escritura atómica: no deja PDFs a medias
    return paginas, omitidos


def procesar(raiz: Path, prefijo: str, minimo: int, recursivo: bool, simulacro: bool) -> int:
    PdfReader, PdfWriter = _cargar_lector_escritor()

    carpetas = [Path(dp) for dp, _dn, _fn in os.walk(raiz)] if recursivo else [raiz]
    carpetas.sort(key=lambda p: clave_natural(str(p)))

    generados = 0
    total_paginas = 0
    saltadas = 0
    con_error: list[str] = []

    print("=" * 64)
    print("  UNIR PDFS — un PDF consolidado por carpeta")
    print("=" * 64)
    print(f"  Raíz: {raiz}")
    print(
        f"  Modo: {'SIMULACRO (no escribe nada)' if simulacro else 'real'}"
        f" | mínimo {minimo} PDF por carpeta"
        f" | {'con subcarpetas' if recursivo else 'solo la raíz'}"
    )
    print("-" * 64)

    for carpeta in carpetas:
        pdfs = listar_pdfs(carpeta, prefijo)
        rel = carpeta.name if carpeta != raiz else "(carpeta raíz)"
        if len(pdfs) < minimo:
            if pdfs:  # había algo pero no alcanza el mínimo
                saltadas += 1
                print(f"  ·  {rel}: {len(pdfs)} PDF (menos de {minimo}, se omite)")
            continue

        base = carpeta.name or "SALIDA"
        destino = carpeta / f"{prefijo}{base}.pdf"

        if simulacro:
            print(f"  →  {rel}: uniría {len(pdfs)} PDF  →  {destino.name}")
            generados += 1
            continue

        paginas, omitidos = unir_pdfs(pdfs, destino, PdfReader, PdfWriter)
        if paginas == 0:
            print(f"  ✗  {rel}: no se pudo leer ningún PDF, se omite")
            con_error.append(str(carpeta))
            continue
        generados += 1
        total_paginas += paginas
        detalle = f"({len(pdfs)} PDF, {paginas} págs.)"
        if omitidos:
            detalle += f"  [omitidos: {', '.join(omitidos)}]"
            con_error.append(str(carpeta))
        print(f"  ✓  {rel}: {destino.name} {detalle}")

    print("-" * 64)
    verbo = "se unirían" if simulacro else "generados"
    print(
        f"  Resumen: {generados} PDF consolidados {verbo}"
        f"{'' if simulacro else f', {total_paginas} páginas en total'}."
    )
    if saltadas:
        print(f"           {saltadas} carpeta(s) con menos de {minimo} PDF, omitidas.")
    if con_error:
        print(f"           {len(con_error)} carpeta(s) con algún PDF ilegible (revisa arriba).")
    if generados == 0 and saltadas == 0:
        print("           No se encontraron PDF para unir en esta carpeta ni en sus subcarpetas.")
    print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Une los PDF de cada carpeta en un solo PDF consolidado.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "raiz", nargs="?", default=".", help="Carpeta a procesar (por defecto, la actual)."
    )
    parser.add_argument(
        "--minimo",
        type=int,
        default=2,
        help="Mínimo de PDF en una carpeta para unirla (por defecto 2).",
    )
    parser.add_argument(
        "--prefijo", default="_UNIDO_", help="Prefijo del PDF resultante (por defecto _UNIDO_)."
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
    if args.minimo < 1:
        sys.stderr.write("ERROR: --minimo debe ser 1 o más.\n")
        return 2

    return procesar(
        raiz=raiz,
        prefijo=args.prefijo,
        minimo=args.minimo,
        recursivo=not args.sin_recursion,
        simulacro=args.simulacro,
    )


if __name__ == "__main__":
    raise SystemExit(main())
