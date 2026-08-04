@echo off
REM ====================================================================
REM  COMPRIMIR_ZIP.cmd  -  Bot de doble clic para el Motor Glosas HUS.
REM  Baja el peso de los archivos .zip de la carpeta donde este ubicado
REM  este archivo (y sus subcarpetas), recomprimiendo su CONTENIDO:
REM  los PDF (escaneos a 150 dpi) y las imagenes (.jpg/.png). Word,
REM  Excel y lo demas se dejan igual. Vuelve a armar el zip al maximo.
REM
REM  El resultado se guarda como <nombre>_LIGERO.zip SOLO si de verdad
REM  pesa menos y quedo integro. El .zip original NUNCA se toca.
REM  (Un .zip ya esta comprimido: el peso baja por su contenido, no por
REM  recomprimir el zip en si; si el contenido ya estaba al minimo, avisa.)
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
title COMPRIMIR ZIP - Motor Glosas HUS

REM Carpeta donde vive este .cmd (sin la barra final, para no romper el "").
set "RAIZ=%~dp0"
if "%RAIZ:~-1%"=="\" set "RAIZ=%RAIZ:~0,-1%"

echo.
echo ============================================================
echo   COMPRIMIR ZIP  -  baja el peso de los .zip recomprimiendo el contenido
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
set "MOTOR=%~dp0comprimir_zip.py"
if exist "%MOTOR%" goto run
set "MOTOR=%~dp0tools\comprimir_zip.py"
if exist "%MOTOR%" goto run
set "MOTOR=%TEMP%\comprimir_zip_hus.py"
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
if "%RC%"=="0" ( echo [OK] Listo. Los zip aligerados quedaron como <nombre>_LIGERO.zip (el original intacto). ) else ( echo [ATENCION] Termino con codigo %RC% - revisa los mensajes de arriba. )
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
echo         Copia tambien "comprimir_zip.py" junto a este .cmd.
echo.
pause
exit /b 3

REM ====================================================================
REM  A partir del marcador de la linea siguiente va el MOTOR en Python
REM  (copia embebida de tools\comprimir_zip.py, salvo el fin de linea).
REM  cmd.exe NUNCA llega aqui: el script termina con "exit /b" mas
REM  arriba. Esta copia solo se usa si el .cmd viaja solo, sin el .py
REM  al lado.
REM ====================================================================
#PYSTART#
"""comprimir_zip.py — Baja el peso de archivos .zip recomprimiendo su contenido.

Un .zip ya está comprimido, así que "recomprimir el zip" no ayuda: el peso se
baja comprimiendo los archivos de ADENTRO. Este bot, por cada .zip de la
carpeta (y subcarpetas):

  1. Lo extrae a una carpeta temporal.
  2. Recomprime los PDF (escaneos a 150 dpi + JPEG, como UNIR_PDFS) y las
     imágenes (.jpg/.jpeg/.png). Word, Excel y lo demás se dejan igual.
  3. Vuelve a armar el zip al máximo nivel de compresión.
  4. Guarda el resultado como `<nombre>_LIGERO.zip` SOLO si de verdad pesa
     menos y quedó íntegro (mismo número de archivos, abre bien).

El .zip original NUNCA se toca. Los `_LIGERO.zip` se ignoran en corridas
siguientes (no se recomprimen sobre sí mismos).

Red de seguridad: cada PDF/imagen solo se reemplaza si su versión recomprimida
pesa menos; ante cualquier fallo se conserva el archivo original dentro del zip.

USO:
    py tools\\comprimir_zip.py "D:\\USUARIO CARTERA\\Documents\\ENVIOS"
    py tools\\comprimir_zip.py .                 # carpeta actual
    py tools\\comprimir_zip.py . --simulacro     # solo mostrar, sin escribir
    py tools\\comprimir_zip.py . --sin-recursion # solo la carpeta raíz
    py tools\\comprimir_zip.py . --reemplazar    # sobrescribir el zip original

Normalmente NO se ejecuta a mano: el archivo `COMPRIMIR_ZIP.cmd` lo lanza con
doble clic. Requiere pymupdf (PDF) y Pillow (imágenes); el lanzador los instala.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

SUFIJO = "_LIGERO"
EXT_IMAGEN = (".jpg", ".jpeg", ".png")
MAX_LADO = 2000  # px del lado largo para imágenes muy grandes


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB"


def clave_natural(nombre: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nombre)]


def recomprimir_pdf(ruta: Path) -> bool:
    """Recomprime un PDF in situ. True si quedó más liviano y válido."""
    try:
        import fitz  # pymupdf
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
    """Recomprime una imagen in situ (mismo formato). True si quedó más liviana."""
    try:
        from PIL import Image
    except ImportError:
        return False
    ext = ruta.suffix.lower()
    if ext not in EXT_IMAGEN:
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
            if ext in (".jpg", ".jpeg"):
                im.convert("RGB").save(tmp, "JPEG", quality=80, optimize=True, progressive=True)
            else:  # .png
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


def _rearmar_zip(origen_zip: Path, carpeta: Path, destino_zip: Path) -> int:
    """Reescribe destino_zip con el contenido de `carpeta`, preservando los
    nombres/orden del zip original. Devuelve el número de archivos escritos."""
    with zipfile.ZipFile(origen_zip) as zin:
        infos = zin.infolist()
    escritos = 0
    with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
        for info in infos:
            if info.is_dir():
                zout.writestr(info, b"")
                continue
            local = carpeta / info.filename
            if not local.exists():
                # nombre no materializado en disco: copiar el original tal cual
                with zipfile.ZipFile(origen_zip) as zin:
                    zout.writestr(info.filename, zin.read(info.filename))
                escritos += 1
                continue
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            zout.writestr(zi, local.read_bytes())
            escritos += 1
    return escritos


def procesar_zip(zip_path: Path, simulacro: bool, reemplazar: bool) -> tuple[int, int, int] | None:
    """Recomprime un zip. Devuelve (antes, despues, n_recomprimidos) o None."""
    antes = zip_path.stat().st_size
    try:
        with zipfile.ZipFile(zip_path) as z:
            if z.testzip() is not None:
                return None
            nombres = z.namelist()
            n_orig = len([n for n in nombres if not n.endswith("/")])
            cifrado = any(getattr(i, "flag_bits", 0) & 0x1 for i in z.infolist())
    except (zipfile.BadZipFile, OSError):
        return None
    if cifrado:
        return None

    if simulacro:
        return antes, antes, 0  # el resumen lo marca aparte

    with TemporaryDirectory(prefix="zip_hus_") as td:
        tmpdir = Path(td)
        try:
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(tmpdir)
        except Exception:
            return None

        recomprimidos = 0
        for dp, _dn, fn in os.walk(tmpdir):
            for nombre in fn:
                f = Path(dp) / nombre
                ext = f.suffix.lower()
                if (
                    ext == ".pdf"
                    and recomprimir_pdf(f)
                    or ext in EXT_IMAGEN
                    and recomprimir_imagen(f)
                ):
                    recomprimidos += 1

        salida_tmp = zip_path.with_name(zip_path.stem + SUFIJO + ".zip.tmp")
        try:
            _rearmar_zip(zip_path, tmpdir, salida_tmp)
            # verificación de integridad del nuevo zip
            with zipfile.ZipFile(salida_tmp) as zc:
                if zc.testzip() is not None:
                    raise ValueError("zip nuevo corrupto")
                n_nuevo = len([n for n in zc.namelist() if not n.endswith("/")])
            if n_nuevo != n_orig:
                raise ValueError("cambió el número de archivos")
            despues = salida_tmp.stat().st_size
            if despues >= antes:  # no vale la pena
                salida_tmp.unlink()
                return antes, antes, recomprimidos
            destino = (
                zip_path if reemplazar else zip_path.with_name(zip_path.stem + SUFIJO + ".zip")
            )
            os.replace(salida_tmp, destino)
            return antes, despues, recomprimidos
        except Exception:
            with contextlib.suppress(OSError):
                salida_tmp.unlink()
            return None


def procesar(raiz: Path, recursivo: bool, simulacro: bool, reemplazar: bool) -> int:
    if recursivo:
        zips = [
            Path(dp) / n for dp, _d, fn in os.walk(raiz) for n in fn if n.lower().endswith(".zip")
        ]
    else:
        zips = [p for p in raiz.iterdir() if p.is_file() and p.suffix.lower() == ".zip"]
    # no re-procesar los _LIGERO que ya generamos
    zips = [z for z in zips if not z.stem.upper().endswith(SUFIJO)]
    zips.sort(key=lambda p: clave_natural(str(p)))

    print("=" * 64)
    print("  COMPRIMIR ZIP — baja el peso recomprimiendo el contenido")
    print("=" * 64)
    print(f"  Raíz: {raiz}")
    print(
        f"  Modo: {'SIMULACRO' if simulacro else 'real'}"
        f" | {'con subcarpetas' if recursivo else 'solo la raíz'}"
        f" | {'REEMPLAZA el original' if reemplazar else 'crea _LIGERO.zip'}"
    )
    print("-" * 64)

    hechos = 0
    sin_margen = 0
    con_error = 0
    ahorro_total = 0
    for z in zips:
        rel = z.name
        if simulacro:
            r = procesar_zip(z, simulacro=True, reemplazar=reemplazar)
            estado = "se analizaría" if r else "no se puede leer (¿cifrado/corrupto?)"
            print(f"  →  {rel}: {estado}")
            continue
        r = procesar_zip(z, simulacro=False, reemplazar=reemplazar)
        if r is None:
            con_error += 1
            print(f"  ✗  {rel}: no se pudo procesar (¿cifrado o corrupto?), se omite")
            continue
        antes, despues, ncomp = r
        if despues < antes:
            hechos += 1
            ahorro_total += antes - despues
            pct = 100 * (antes - despues) / antes
            print(
                f"  ✓  {rel}: {_mb(antes)} → {_mb(despues)}  (-{pct:.0f}%, {ncomp} archivos recomprimidos)"
            )
        else:
            sin_margen += 1
            print(f"  ·  {rel}: {_mb(antes)} — ya estaba al mínimo, sin margen")

    print("-" * 64)
    if not simulacro:
        print(f"  Resumen: {hechos} zip aligerados, se ahorraron {_mb(ahorro_total)} en total.")
        if not reemplazar and hechos:
            print(
                "           Los aligerados quedaron como <nombre>_LIGERO.zip (el original intacto)."
            )
        if sin_margen:
            print(f"           {sin_margen} zip sin margen (su contenido ya estaba comprimido).")
        if con_error:
            print(f"           {con_error} zip no se pudieron procesar (cifrados o dañados).")
    if not zips:
        print("           No se encontraron archivos .zip en esta carpeta ni en sus subcarpetas.")
    print("=" * 64)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Baja el peso de archivos .zip recomprimiendo su contenido (PDF e imágenes).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "raiz", nargs="?", default=".", help="Carpeta a procesar (por defecto, la actual)."
    )
    parser.add_argument(
        "--sin-recursion", action="store_true", help="Procesar solo la carpeta raíz."
    )
    parser.add_argument(
        "--reemplazar",
        action="store_true",
        help="Sobrescribir el zip original en vez de crear <nombre>_LIGERO.zip.",
    )
    parser.add_argument(
        "--simulacro", "--dry-run", action="store_true", help="Mostrar qué haría, sin escribir."
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
        reemplazar=args.reemplazar,
    )


if __name__ == "__main__":
    raise SystemExit(main())
