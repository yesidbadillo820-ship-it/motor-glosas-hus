"""evidencias_a_word.py — Une los pantallazos de cierre de COOSALUD en un Word.

Lee todos los `.png` de una carpeta (típicamente la de EVIDENCIA del bot de
COOSALUD, donde cada archivo se llama `HUS<numero>_cierre.png`) y arma un .docx
con UNA factura por página: encabezado con el número de factura + la imagen
escalada al ancho de página + salto de página.

USO:
    py evidencias_a_word.py ^
        --carpeta "D:\\USUARIO CARTERA\\Documents\\COOSALUD\\EVIDENCIA" ^
        --salida  "D:\\USUARIO CARTERA\\Documents\\COOSALUD\\evidencias.docx"

DEPENDENCIAS:
    py -m pip install python-docx
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger("evidencias_word")

# HUS123456 al principio del nombre del PNG → encabezado de la factura.
RE_FACTURA = re.compile(r"^(HUS\d{5,9})", re.IGNORECASE)


def _factura_desde_nombre(p: Path) -> str:
    """HUS508259_cierre.png → 'HUS508259'. Si no matchea, usa el stem completo."""
    m = RE_FACTURA.match(p.name)
    return m.group(1).upper() if m else p.stem


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--carpeta", type=Path, required=True, help="Carpeta con los PNG de evidencia.")
    parser.add_argument("--salida", type=Path, required=True, help="Archivo .docx de salida.")
    parser.add_argument(
        "--patron",
        type=str,
        default="*.png",
        help="Glob de archivos (default *.png; ejemplo --patron '*_cierre.png').",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
        from docx.shared import Cm, Pt
    except ImportError:
        sys.stderr.write("ERROR: falta python-docx. Instalalo con: py -m pip install python-docx\n")
        return 2

    if not args.carpeta.is_dir():
        logger.error(f"No es una carpeta: {args.carpeta}")
        return 1

    imagenes = sorted(args.carpeta.glob(args.patron))
    if not imagenes:
        logger.error(f"No encontré imágenes ({args.patron}) en {args.carpeta}")
        return 1
    logger.info(f"Imágenes a incluir: {len(imagenes)}")

    doc = Document()
    # Márgenes razonables (Word default tiende a 2.54cm, dejamos 1.5).
    for sec in doc.sections:
        sec.top_margin = Cm(1.5)
        sec.bottom_margin = Cm(1.5)
        sec.left_margin = Cm(1.8)
        sec.right_margin = Cm(1.8)
    # Ancho disponible para la imagen (página A4 21cm − márgenes).
    ancho_imagen = Cm(17.0)

    for i, img in enumerate(imagenes):
        factura = _factura_desde_nombre(img)
        # Encabezado: número de factura, grande y centrado.
        h = doc.add_paragraph()
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = h.add_run(factura)
        run.bold = True
        run.font.size = Pt(20)
        # Imagen centrada, ancho fijo (Word escala alto manteniendo aspecto).
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        try:
            p_img.add_run().add_picture(str(img), width=ancho_imagen)
        except Exception as e:
            logger.warning(f"  {img.name}: no se pudo insertar — {e}")
            continue
        # Salto de página (menos en la última).
        if i < len(imagenes) - 1:
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        logger.info(f"  [{i+1}/{len(imagenes)}] {factura} ← {img.name}")

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(args.salida))
    logger.info(f"\nWord generado: {args.salida}")
    logger.info(f"  Páginas: {len(imagenes)} (una factura por página)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
