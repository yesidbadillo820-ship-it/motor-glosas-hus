"""Consolida varias imágenes (PNG/JPG) en un único PDF multipágina.

Pensado para juntar los pantallazos de evidencia que deja
responder_glosas_simed.py (uno por factura cargada) en un solo PDF para
adjuntar a la EPS.

Uso típico:

    py tools\\evidencias_a_pdf.py --lista lista.txt --salida GI-33-5096-2026.pdf
    py tools\\evidencias_a_pdf.py --paginas a.png b.png c.png --salida out.pdf

Orden de las páginas:
- Con --lista: el del archivo (una ruta por línea), conserva el orden de lectura.
- Con --paginas: el de la línea de comandos.
- Con --carpeta: ordenado por nombre de archivo ascendente.

Requiere Pillow (`pip install Pillow`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _exigir_pillow():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print(
            "ERROR: este script requiere Pillow.\n       pip install Pillow",
            file=sys.stderr,
        )
        sys.exit(2)


def leer_lista(ruta: Path) -> list[Path]:
    items: list[Path] = []
    for ln in ruta.read_text(encoding="utf-8-sig").splitlines():
        s = ln.strip().strip('"').strip("'")
        if not s or s.startswith("#"):
            continue
        items.append(Path(s))
    return items


def reunir_paginas(args) -> list[Path]:
    if args.lista is not None:
        return leer_lista(args.lista)
    if args.paginas:
        return [Path(p) for p in args.paginas]
    if args.carpeta is not None:
        if not args.carpeta.is_dir():
            print(f"ERROR: --carpeta no es directorio: {args.carpeta}", file=sys.stderr)
            sys.exit(2)
        exts = {".png", ".jpg", ".jpeg"}
        return sorted(p for p in args.carpeta.iterdir() if p.suffix.lower() in exts)
    print("ERROR: pasá --lista, --paginas o --carpeta.", file=sys.stderr)
    sys.exit(2)


def consolidar(paginas: list[Path], salida: Path) -> None:
    from PIL import Image

    if not paginas:
        print("ERROR: no hay páginas para consolidar.", file=sys.stderr)
        sys.exit(1)

    faltan = [p for p in paginas if not p.is_file()]
    if faltan:
        print("ERROR: no existen estos archivos:", file=sys.stderr)
        for p in faltan:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)

    imgs = []
    for p in paginas:
        im = Image.open(p)
        if im.mode != "RGB":
            im = im.convert("RGB")
        imgs.append(im)

    salida.parent.mkdir(parents=True, exist_ok=True)
    first, rest = imgs[0], imgs[1:]
    first.save(str(salida), save_all=True, append_images=rest, format="PDF")
    print(f"OK: {len(imgs)} paginas -> {salida}")


def main() -> int:
    _exigir_pillow()
    p = argparse.ArgumentParser(
        description="Consolida PNG/JPG en un solo PDF multipagina.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    fuente = p.add_mutually_exclusive_group(required=True)
    fuente.add_argument(
        "--lista", type=Path, help="TXT con una ruta por linea (preserva el orden)."
    )
    fuente.add_argument("--paginas", nargs="+", help="Rutas inline separadas por espacio.")
    fuente.add_argument("--carpeta", type=Path, help="Carpeta con PNG/JPG, ordenadas por nombre.")
    p.add_argument("--salida", type=Path, required=True, help="Ruta del PDF de salida.")
    args = p.parse_args()

    paginas = reunir_paginas(args)
    salida = args.salida
    if salida.suffix.lower() != ".pdf":
        salida = salida.with_suffix(".pdf")
    consolidar(paginas, salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
