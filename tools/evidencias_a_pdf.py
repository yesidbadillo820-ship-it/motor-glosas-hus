"""evidencias_a_pdf.py — Une los pantallazos de evidencia en un solo PDF.

Lee `.png` de evidencia (p.ej. la carpeta del bot de FOMAG, donde cada archivo
se llama `HUS<numero>_ratificada.png`) y arma un PDF con UNA factura por página:
un encabezado con el número de factura + la imagen de la evidencia debajo.

Pensado para consolidar las evidencias de un cargue en un único archivo para
radicar (ej. nombre `GR-33-2070-2026.pdf`).

Dos modos para elegir las imágenes:

  --carpeta  toma todos los archivos que matcheen `--patron` (default *.png)
             dentro de la carpeta, ordenados por nombre (orden natural).
  --lista    toma rutas explícitas desde un TXT (1 ruta por línea, se respeta
             el orden del TXT). Útil para un subset o un orden específico.

USO:
    REM Consolidar toda la carpeta de evidencias en un PDF para radicar
    py evidencias_a_pdf.py ^
        --carpeta "C:\\temp-notas\\EVIDENCIA_FOMAG" ^
        --salida  "Z:\\...\\GR-33-2070-2026.pdf"

    REM Solo un subset, en el orden de un TXT
    py evidencias_a_pdf.py ^
        --lista   "C:\\temp-notas\\lote.txt" ^
        --salida  "Z:\\...\\GR-33-2070-2026.pdf"

DEPENDENCIAS:
    py -m pip install pillow
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger("evidencias_pdf")

RE_FACTURA = re.compile(r"^(HUS\d{5,9})", re.IGNORECASE)


def _exigir_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
        return Image, ImageDraw, ImageFont
    except ImportError:
        sys.stderr.write(
            "ERROR: falta Pillow.\n"
            "    py -m pip install pillow\n"
        )
        sys.exit(2)


def _factura_desde_nombre(p: Path) -> str:
    """HUS512134_ratificada.png → 'HUS512134'. Si no matchea, usa el stem."""
    m = RE_FACTURA.match(p.name)
    return m.group(1).upper() if m else p.stem


def _clave_natural(p: Path):
    """Orden natural: separa números para que HUS9 < HUS10 (acá todos miden
    igual, pero es robusto)."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", p.name)]


def _leer_lista(p: Path) -> list[Path]:
    """Lee un TXT con 1 ruta por línea. Ignora vacías, comentarios (#) y quita
    comillas envolventes. Preserva el orden del TXT."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = p.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"No pude decodificar la lista: {p}")
    rutas: list[Path] = []
    for linea in texto.splitlines():
        s = linea.strip().strip('"').strip("'")
        if not s or s.startswith("#"):
            continue
        rutas.append(Path(s))
    return rutas


def _cargar_fuente(ImageFont, tam: int):
    """Intenta una TTF legible (Arial en Windows); si no, la default de PIL."""
    for nombre in ("arial.ttf", "Arial.ttf", "C:/Windows/Fonts/arial.ttf",
                   "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nombre, tam)
        except Exception:
            continue
    return ImageFont.load_default()


def _pagina_con_encabezado(Image, ImageDraw, ImageFont, png: Path,
                           titulo: str, sin_encabezado: bool):
    """Devuelve una imagen RGB: encabezado (si aplica) + el pantallazo debajo."""
    im = Image.open(png)
    if im.mode != "RGB":
        im = im.convert("RGB")
    if sin_encabezado:
        return im
    alto_enc = 64
    fondo = (243, 246, 250)
    pagina = Image.new("RGB", (im.width, im.height + alto_enc), "white")
    draw = ImageDraw.Draw(pagina)
    draw.rectangle([0, 0, im.width, alto_enc], fill=fondo)
    fuente = _cargar_fuente(ImageFont, 26)
    draw.text((20, alto_enc // 2 - 16), titulo, fill=(20, 40, 80), font=fuente)
    pagina.paste(im, (0, alto_enc))
    return pagina


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consolida pantallazos de evidencia (.png) en un único PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--carpeta", type=Path, help="Carpeta con los PNG (ordena por nombre).")
    grupo.add_argument("--lista", type=Path, help="TXT con 1 ruta por línea (preserva el orden).")
    parser.add_argument("--patron", default="*.png", help="Patrón para --carpeta (default *.png).")
    parser.add_argument("--salida", type=Path, required=True, help="PDF de salida (ej. GR-33-2070-2026.pdf).")
    parser.add_argument("--sin-encabezado", action="store_true",
                        help="No agregar la franja con el número de factura.")
    parser.add_argument("--titulo", default="Evidencia de respuesta de glosa ratificada — FOMAG/Horus",
                        help="Texto que acompaña al número de factura en el encabezado.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    Image, ImageDraw, ImageFont = _exigir_pillow()

    # Resolver la lista de imágenes.
    if args.carpeta is not None:
        if not args.carpeta.is_dir():
            logger.error(f"No existe la carpeta: {args.carpeta}")
            return 1
        pngs = sorted(args.carpeta.glob(args.patron), key=_clave_natural)
    else:
        if not args.lista.is_file():
            logger.error(f"No existe la lista: {args.lista}")
            return 1
        pngs = _leer_lista(args.lista)

    # Validar que existan.
    existentes: list[Path] = []
    for p in pngs:
        if p.is_file():
            existentes.append(p)
        else:
            logger.warning(f"⚠ no existe, lo salto: {p}")
    if not existentes:
        logger.error("No hay imágenes para consolidar.")
        return 1

    logger.info(f"Consolidando {len(existentes)} evidencia(s) en {args.salida.name}…")
    paginas = []
    for i, png in enumerate(existentes, start=1):
        factura = _factura_desde_nombre(png)
        titulo = f"{factura}    {args.titulo}"
        try:
            paginas.append(_pagina_con_encabezado(
                Image, ImageDraw, ImageFont, png, titulo, args.sin_encabezado))
            logger.info(f"  [{i}/{len(existentes)}] {factura}  ({png.name})")
        except Exception as e:
            logger.warning(f"  ⚠ no pude procesar {png.name}: {e}")

    if not paginas:
        logger.error("Ninguna imagen se pudo procesar.")
        return 1

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    paginas[0].save(
        str(args.salida), "PDF", save_all=True, append_images=paginas[1:],
        resolution=100.0,
    )
    logger.info(f"\n✅ PDF generado ({len(paginas)} páginas): {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
