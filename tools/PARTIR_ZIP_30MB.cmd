@echo off
REM ====================================================================
REM  PARTIR_ZIP_30MB.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Parte los .zip de la carpeta (y subcarpetas) en pedazos INDEPENDIENTES
REM  de menos de 30 MB cada uno, para poder subirlos a un chat/portal con
REM  tope de tamano:
REM      JULIO.zip  ->  JULIO_parte1_de4.zip, JULIO_parte2_de4.zip, ...
REM  Cada parte se abre por si sola. Primero recomprime el contenido
REM  (PDF e imagenes) para que hagan falta menos partes. Si un solo PDF
REM  ya pesa mas de 30 MB, lo divide por paginas.
REM
REM  El .zip original NUNCA se toca. Sube TODAS las partes al chat; quien
REM  las reciba abre cada una normalmente.
REM
REM  USO:  copia este archivo a la carpeta que tiene tus .zip y dale
REM        doble clic.  Nada mas.
REM
REM  Es autocontenido: lleva el motor Python adentro. Si el equipo no
REM  tiene Python, el bot lo INSTALA SOLO (via winget o python.org, sin
REM  administrador). Solo necesita internet la primera vez.
REM ====================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
title PARTIR ZIP 30MB - Motor Glosas HUS

REM Carpeta donde vive este .cmd (sin la barra final, para no romper el "").
set "RAIZ=%~dp0"
if "%RAIZ:~-1%"=="\" set "RAIZ=%RAIZ:~0,-1%"

echo.
echo ============================================================
echo   PARTIR ZIP 30MB  -  parte los .zip en pedazos de menos de 30 MB
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
REM --- Asegurar componentes: pymupdf (PDF) y Pillow (imagenes) ---------
%PYEXE% -c "import fitz" >nul 2>&1 || ( echo [i] Instalando compresor de PDF pymupdf por unica vez, espera... & %PYEXE% -m pip install --quiet --user pymupdf >nul 2>&1 )
%PYEXE% -c "import PIL"  >nul 2>&1 || ( echo [i] Instalando compresor de imagenes Pillow por unica vez, espera... & %PYEXE% -m pip install --quiet --user pillow >nul 2>&1 )
REM --- 2) Localizar el motor Python -----------------------------------
REM  Preferimos el .py al lado (o en tools\); si el .cmd viaja solo,
REM  extraemos la copia embebida que va despues del marcador.
set "MOTOR=%~dp0partir_zip.py"
if exist "%MOTOR%" goto run
set "MOTOR=%~dp0tools\partir_zip.py"
if exist "%MOTOR%" goto run
set "MOTOR=%TEMP%\partir_zip_hus.py"
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
%PYEXE% "%MOTOR%" "%RAIZ%" --max-mb 30 %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo [OK] Listo. Cada zip quedo partido en <nombre>_parteN_deM.zip - subelas TODAS al chat. ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
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
echo         Copia tambien "partir_zip.py" junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  A partir del marcador de la linea siguiente va el MOTOR en Python
REM  (copia embebida de tools\partir_zip.py, salvo el fin de linea).
REM  cmd.exe NUNCA llega aqui: el script termina con "exit /b" mas
REM  arriba. Esta copia solo se usa si el .cmd viaja solo, sin el .py
REM  al lado.
REM ====================================================================
#PYSTART#
"""partir_zip.py — Parte un .zip en pedazos independientes de menos de N MB.

Pensado para SUBIR soportes a un chat/portal con tope de tamaño (por defecto
< 30 MB por archivo). Por cada .zip de la carpeta:

  1. Lo extrae a un temporal y recomprime su contenido (PDF a 150 dpi e
     imágenes .jpg/.png), como COMPRIMIR_ZIP. Word/Excel/otros se dejan igual.
  2. Reparte los archivos en varios zips INDEPENDIENTES, cada uno < N MB:
        JULIO_parte1_de_4.zip, JULIO_parte2_de_4.zip, ...
     Cada parte se abre por sí sola (no es un zip multivolumen).
  3. Si un solo PDF ya pesa más que el tope, lo divide por páginas
     (FACTURA.pdf -> FACTURA_p1.pdf, FACTURA_p2.pdf) para que quepa.

El .zip original NUNCA se toca. Los archivos que genera (*_parte*_de_*.zip) se
ignoran en corridas siguientes.

USO:
    py tools\\partir_zip.py "D:\\USUARIO CARTERA\\Documents\\07 JULIO"
    py tools\\partir_zip.py .                 # carpeta actual
    py tools\\partir_zip.py . --max-mb 30     # tope por parte (por defecto 29)
    py tools\\partir_zip.py . --sin-comprimir # solo partir, sin recomprimir
    py tools\\partir_zip.py . --simulacro     # solo mostrar, sin escribir

Normalmente NO se ejecuta a mano: el archivo `PARTIR_ZIP_30MB.cmd` lo lanza con
doble clic. Requiere pymupdf (PDF) y Pillow (imágenes); el lanzador los instala.
"""

from __future__ import annotations

import argparse
import contextlib
import math
import os
import re
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

EXT_IMAGEN = (".jpg", ".jpeg", ".png")
MAX_LADO = 2000
MARCA_PARTE = re.compile(r"_parte\d+_de\d+$", re.IGNORECASE)


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB"


def clave_natural(nombre: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nombre)]


def recomprimir_pdf(ruta: Path) -> bool:
    try:
        import fitz
    except ImportError:
        return False
    antes = ruta.stat().st_size
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    with contextlib.suppress(Exception):
        fitz.TOOLS.mupdf_display_errors(False)
    try:
        with fitz.open(str(ruta)) as doc:
            paginas = doc.page_count
            if paginas == 0:
                return False
            if hasattr(doc, "rewrite_images"):
                doc.rewrite_images(dpi_threshold=200, dpi_target=150, quality=80)
            doc.save(str(tmp), garbage=4, deflate=True, clean=True)
        with fitz.open(str(tmp)) as chk:
            if chk.page_count != paginas:
                raise ValueError("no conserva páginas")
        if tmp.stat().st_size < antes:
            os.replace(tmp, ruta)
            return True
        tmp.unlink()
        return False
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        return False


def recomprimir_imagen(ruta: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    if ruta.suffix.lower() not in EXT_IMAGEN:
        return False
    antes = ruta.stat().st_size
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    try:
        with Image.open(ruta) as im:
            im.load()
            w, h = im.size
            escala = min(1.0, MAX_LADO / max(w, h))
            if escala < 1.0:
                im = im.resize((max(int(w * escala), 1), max(int(h * escala), 1)), Image.LANCZOS)
            if ruta.suffix.lower() in (".jpg", ".jpeg"):
                im.convert("RGB").save(tmp, "JPEG", quality=80, optimize=True, progressive=True)
            else:
                im.save(tmp, "PNG", optimize=True)
        if tmp.stat().st_size < antes:
            os.replace(tmp, ruta)
            return True
        tmp.unlink()
        return False
    except Exception:
        with contextlib.suppress(OSError):
            tmp.unlink()
        return False


def _split_pdf_por_paginas(ruta: Path, rel: str, limite: int) -> list[tuple[str, Path]]:
    """Divide un PDF grande en varios que quepan bajo `limite`. Devuelve la lista
    (nombre_relativo, ruta_en_disco). Si no se puede, devuelve el original."""
    try:
        import fitz
    except ImportError:
        return [(rel, ruta)]
    size = ruta.stat().st_size
    if size <= limite:
        return [(rel, ruta)]
    try:
        with fitz.open(str(ruta)) as doc:
            n = doc.page_count
            if n <= 1:
                return [(rel, ruta)]  # una sola página: no se puede partir más
            partes: list[tuple[str, Path]] = []
            # cortar en trozos de páginas; subdividir si un trozo aún excede
            objetivo = max(1, math.floor(n / math.ceil(size / limite)))
            base = ruta.with_suffix("")  # sin .pdf
            idx = 0
            i = 0
            while i < n:
                idx += 1
                j = min(i + objetivo, n)
                sub = fitz.open()
                sub.insert_pdf(doc, from_page=i, to_page=j - 1)
                dest = Path(f"{base}_p{idx}.pdf")
                sub.save(str(dest), garbage=4, deflate=True)
                sub.close()
                # si el trozo aún pesa de más y tiene varias páginas, reducir el objetivo
                if dest.stat().st_size > limite and (j - i) > 1:
                    dest.unlink()
                    objetivo = max(1, (j - i) // 2)
                    idx -= 1
                    continue
                rel_sub = rel[:-4] + f"_p{idx}.pdf"  # rel termina en .pdf
                partes.append((rel_sub, dest))
                i = j
        ruta.unlink()  # ya no se usa el grande
        return partes
    except Exception:
        return [(rel, ruta)]


def _empacar(archivos: list[tuple[str, Path]], limite: int) -> list[list[tuple[str, Path]]]:
    """Reparte (rel, ruta) en grupos cuyo tamaño sumado no pase `limite`
    (greedy, de mayor a menor). Un archivo que solo ya excede va en su grupo."""
    archivos = sorted(archivos, key=lambda t: t[1].stat().st_size, reverse=True)
    grupos: list[list[tuple[str, Path]]] = []
    tam: list[int] = []
    for rel, ruta in archivos:
        s = ruta.stat().st_size
        colocado = False
        for k in range(len(grupos)):
            if tam[k] + s <= limite:
                grupos[k].append((rel, ruta))
                tam[k] += s
                colocado = True
                break
        if not colocado:
            grupos.append([(rel, ruta)])
            tam.append(s)
    return grupos


def procesar_zip(zip_path: Path, limite: int, comprimir: bool, simulacro: bool) -> dict | None:
    antes = zip_path.stat().st_size
    try:
        with zipfile.ZipFile(zip_path) as z:
            if z.testzip() is not None:
                return None
            if any(getattr(i, "flag_bits", 0) & 0x1 for i in z.infolist()):
                return None
    except (zipfile.BadZipFile, OSError):
        return None

    if simulacro:
        n = max(1, math.ceil(antes / limite))
        return {"antes": antes, "partes": [], "estimado": n}

    with TemporaryDirectory(prefix="partir_hus_") as td:
        tmp = Path(td)
        try:
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(tmp)
        except Exception:
            return None

        # Margen para el overhead del zip (cabeceras) y para que el contenido
        # ya comprimido no haga que la parte final pase del tope real. 4% cubre
        # de sobra el overhead real (unos KB); en 30 MB son ~1.2 MB de colchón.
        limite_ef = max(1, limite - max(8192, limite * 4 // 100))

        # lista de archivos (rel, ruta), recomprimiendo si aplica
        archivos: list[tuple[str, Path]] = []
        for dp, _dn, fn in os.walk(tmp):
            for nombre in fn:
                f = Path(dp) / nombre
                rel = str(f.relative_to(tmp)).replace(os.sep, "/")
                if comprimir:
                    ext = f.suffix.lower()
                    if ext == ".pdf":
                        recomprimir_pdf(f)
                    elif ext in EXT_IMAGEN:
                        recomprimir_imagen(f)
                # partir PDFs que por sí solos excedan el tope efectivo
                if f.suffix.lower() == ".pdf" and f.stat().st_size > limite_ef:
                    archivos.extend(_split_pdf_por_paginas(f, rel, limite_ef))
                else:
                    archivos.append((rel, f))

        grupos = _empacar(archivos, limite_ef)
        total = len(grupos)
        partes_info = []
        base = zip_path.stem
        for k, grupo in enumerate(grupos, start=1):
            dest = zip_path.with_name(f"{base}_parte{k}_de{total}.zip")
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
                for rel, ruta in grupo:
                    zout.write(ruta, rel)
            partes_info.append((dest.name, dest.stat().st_size))
        return {"antes": antes, "partes": partes_info, "estimado": total}


def procesar(raiz: Path, limite: int, comprimir: bool, recursivo: bool, simulacro: bool) -> int:
    if recursivo:
        zips = [
            Path(dp) / n for dp, _d, fn in os.walk(raiz) for n in fn if n.lower().endswith(".zip")
        ]
    else:
        zips = [p for p in raiz.iterdir() if p.is_file() and p.suffix.lower() == ".zip"]
    zips = [z for z in zips if not MARCA_PARTE.search(z.stem)]
    zips.sort(key=lambda p: clave_natural(str(p)))

    print("=" * 64)
    print("  PARTIR ZIP — pedazos independientes que caben en el chat")
    print("=" * 64)
    print(f"  Raíz: {raiz}")
    print(
        f"  Modo: {'SIMULACRO' if simulacro else 'real'}"
        f" | tope {_mb(limite)} por parte"
        f" | {'recomprime el contenido' if comprimir else 'sin recomprimir'}"
    )
    print("-" * 64)

    hechos = 0
    con_error = 0
    grandes = 0
    for z in zips:
        r = procesar_zip(z, limite, comprimir, simulacro)
        if r is None:
            con_error += 1
            print(f"  ✗  {z.name}: no se pudo procesar (¿cifrado o corrupto?), se omite")
            continue
        if simulacro:
            print(f"  →  {z.name}: {_mb(r['antes'])} → ~{r['estimado']} parte(s)")
            continue
        hechos += 1
        print(f"  ✓  {z.name}: {_mb(r['antes'])} → {len(r['partes'])} parte(s)")
        for nombre, tam in r["partes"]:
            aviso = "  ¡AÚN excede el tope!" if tam > limite else ""
            if tam > limite:
                grandes += 1
            print(f"        · {nombre}  ({_mb(tam)}){aviso}")

    print("-" * 64)
    if not simulacro:
        print(f"  Resumen: {hechos} zip partidos en pedazos de menos de {_mb(limite)}.")
        if grandes:
            print(f"           {grandes} parte(s) siguen por encima del tope: contienen un solo")
            print("           archivo (no PDF) que no se puede partir. Avísame y vemos.")
        if con_error:
            print(f"           {con_error} zip no se pudieron procesar (cifrados o dañados).")
    if not zips:
        print("           No se encontraron archivos .zip en esta carpeta ni en sus subcarpetas.")
    print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parte cada .zip en pedazos independientes de menos de N MB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("raiz", nargs="?", default=".", help="Carpeta a procesar.")
    parser.add_argument(
        "--max-mb", type=float, default=29.0, help="Tope de MB por parte (por defecto 29)."
    )
    parser.add_argument(
        "--sin-comprimir", action="store_true", help="Solo partir, sin recomprimir el contenido."
    )
    parser.add_argument("--sin-recursion", action="store_true", help="Solo la carpeta raíz.")
    parser.add_argument(
        "--simulacro", "--dry-run", action="store_true", help="Mostrar qué haría, sin escribir."
    )
    args = parser.parse_args(argv)

    raiz = Path(args.raiz).expanduser().resolve()
    if not raiz.is_dir():
        sys.stderr.write(f"ERROR: no existe la carpeta: {raiz}\n")
        return 2
    if args.max_mb <= 0:
        sys.stderr.write("ERROR: --max-mb debe ser mayor que 0.\n")
        return 2

    limite = int(args.max_mb * 1_000_000)  # MB decimales: margen seguro bajo 30 "MB"
    return procesar(
        raiz=raiz,
        limite=limite,
        comprimir=not args.sin_comprimir,
        recursivo=not args.sin_recursion,
        simulacro=args.simulacro,
    )


if __name__ == "__main__":
    raise SystemExit(main())
