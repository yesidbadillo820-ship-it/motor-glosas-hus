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
