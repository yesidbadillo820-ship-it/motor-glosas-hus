"""dump_pdf.py — Vuelca el texto de un PDF (pdfplumber) para inspección.

Uso:
    py dump_pdf.py "C:\\...\\680010079201_HUS428139_FACTURA.pdf"
    py dump_pdf.py "ruta.pdf" --salida factura_texto.txt   # guarda a archivo

Sirve para ver exactamente cómo pdfplumber extrae el detalle de la factura
(códigos SOAT, nombres, cantidades, valores y la descomposición quirúrgica),
y así construir el parser sobre el texto real.

DEPENDENCIA: pdfplumber (pip install pdfplumber)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def extraer_texto(ruta: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        sys.stderr.write(
            "ERROR: falta pdfplumber.\n  Instalalo con:  py -m pip install pdfplumber\n"
        )
        sys.exit(2)

    partes: list[str] = []
    with pdfplumber.open(str(ruta)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            partes.append(f"\n===== PÁGINA {i} =====")
            partes.append(page.extract_text() or "(sin texto extraíble)")
    return "\n".join(partes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Ruta al PDF")
    parser.add_argument("--salida", type=Path, default=None, help="Guardar el texto en un archivo")
    args = parser.parse_args()

    if not args.pdf.is_file():
        sys.stderr.write(f"No existe el PDF: {args.pdf}\n")
        return 1

    texto = extraer_texto(args.pdf)
    if args.salida:
        args.salida.write_text(texto, encoding="utf-8")
        print(f"Texto guardado en: {args.salida}  ({len(texto)} caracteres)")
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
