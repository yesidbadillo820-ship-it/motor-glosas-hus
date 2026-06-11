"""evidencias_a_word.py — Une los pantallazos de cierre de COOSALUD en un Word.

Lee todos los `.png` de una carpeta (típicamente la de EVIDENCIA del bot de
COOSALUD, donde cada archivo se llama `HUS<numero>_cierre.png`) y arma un .docx
con UNA factura por página: encabezado con el número de factura + la imagen
escalada para que entre completa con el encabezado en una sola hoja A4 +
salto de página.

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
import struct
import sys
from pathlib import Path

logger = logging.getLogger("evidencias_word")

RE_FACTURA = re.compile(r"^(HUS\d{5,9})", re.IGNORECASE)


def _factura_desde_nombre(p: Path) -> str:
    """HUS508259_cierre.png → 'HUS508259'. Si no matchea, usa el stem completo."""
    m = RE_FACTURA.match(p.name)
    return m.group(1).upper() if m else p.stem


def _png_dims_px(path: Path) -> tuple[int, int] | None:
    """Devuelve (ancho_px, alto_px) del PNG leyendo su cabecera IHDR.
    Devuelve None si el archivo no es un PNG válido."""
    try:
        with path.open("rb") as f:
            sig = f.read(8)
            if sig[:4] != b"\x89PNG":
                return None
            f.read(8)  # IHDR length (4) + chunk type (4)
            w, h = struct.unpack(">II", f.read(8))
            return w, h
    except Exception:
        return None


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
    # Márgenes razonables para A4.
    for sec in doc.sections:
        sec.top_margin = Cm(1.5)
        sec.bottom_margin = Cm(1.5)
        sec.left_margin = Cm(1.8)
        sec.right_margin = Cm(1.8)
    # Área útil A4 con esos márgenes: 17.4cm × 26.7cm aprox.
    # Reservamos ~1.5cm para el encabezado + 0.5cm para margen visual: la
    # imagen no debe pasarse de ANCHO_MAX × ALTO_MAX.
    ANCHO_MAX_CM = 17.0
    ALTO_MAX_CM = 24.0

    for i, img in enumerate(imagenes):
        factura = _factura_desde_nombre(img)
        # Encabezado: número de factura, grande, negrita, centrado.
        h = doc.add_paragraph()
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = h.add_run(factura)
        run.bold = True
        run.font.size = Pt(20)
        # Decidir width/height para que la imagen ENTRE en una sola hoja
        # JUNTO con el encabezado (sin salto de página automático).
        dims = _png_dims_px(img)
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        try:
            if dims is None:
                # Fallback: que Word elija — limitamos solo el ancho.
                p_img.add_run().add_picture(str(img), width=Cm(ANCHO_MAX_CM))
            else:
                w_px, h_px = dims
                if w_px <= 0 or h_px <= 0:
                    p_img.add_run().add_picture(str(img), width=Cm(ANCHO_MAX_CM))
                else:
                    # Si fijar ancho=ANCHO_MAX_CM excede ALTO_MAX_CM,
                    # mejor fijamos por alto (la imagen queda más angosta
                    # pero entra completa con el encabezado).
                    alto_si_max_ancho = ANCHO_MAX_CM * (h_px / w_px)
                    if alto_si_max_ancho <= ALTO_MAX_CM:
                        p_img.add_run().add_picture(str(img), width=Cm(ANCHO_MAX_CM))
                    else:
                        p_img.add_run().add_picture(str(img), height=Cm(ALTO_MAX_CM))
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
