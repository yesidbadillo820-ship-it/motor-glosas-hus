"""dump_pdf_tablas.py — Diagnóstico: vuelca las tablas que pdfplumber detecta en un PDF.

Antes de construir un parser basado en tablas, necesitamos saber si pdfplumber
puede extraer la tabla del 'Detalle de Cargos' como filas estructuradas.

Uso:
    py dump_pdf_tablas.py "C:\\...\\680010079201_HUS428139_FACTURA.pdf"
    py dump_pdf_tablas.py "ruta.pdf" --salida tablas.txt

Imprime, por página:
  - Cuántas tablas detectó pdfplumber.
  - Las primeras 10 filas de cada tabla (con columnas separadas por '|').
  - Si NO detecta tablas, prueba con detección por texto-alineado.

Con esa salida decidimos cuál estrategia usar para construir el parser real.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def diagnosticar(pdf_path: Path, salida: Path | None) -> str:
    try:
        import pdfplumber
    except ImportError:
        sys.stderr.write(
            "ERROR: falta pdfplumber.\n  Instalalo con:  py -m pip install pdfplumber\n"
        )
        sys.exit(2)

    out: list[str] = []

    def w(s: str = "") -> None:
        out.append(s)

    with pdfplumber.open(str(pdf_path)) as pdf:
        w(f"PDF: {pdf_path.name}  ({len(pdf.pages)} páginas)")
        w("=" * 70)

        for i, page in enumerate(pdf.pages, 1):
            w(f"\n----- PÁGINA {i} -----")
            # Estrategia 1: detección por defecto (líneas dibujadas)
            try:
                tablas = page.extract_tables() or []
            except Exception as e:
                tablas = []
                w(f"  extract_tables() falló: {e}")

            w(f"  Estrategia 1 (lines): {len(tablas)} tabla(s)")
            for ti, t in enumerate(tablas, 1):
                w(f"    Tabla {ti}: {len(t)} filas × {len(t[0]) if t else 0} columnas")
                for fi, fila in enumerate(t[:10], 1):
                    cells = [str(c).strip().replace("\n", " ")[:30] if c else "" for c in fila]
                    w(f"      [{fi:>2}] " + " | ".join(cells))
                if len(t) > 10:
                    w(f"      ... ({len(t) - 10} filas más)")

            # Estrategia 2: detección por texto alineado (sin líneas)
            if not tablas:
                try:
                    tablas2 = (
                        page.extract_tables(
                            table_settings={
                                "vertical_strategy": "text",
                                "horizontal_strategy": "text",
                                "snap_tolerance": 3,
                            }
                        )
                        or []
                    )
                except Exception as e:
                    tablas2 = []
                    w(f"  extract_tables(text) falló: {e}")

                w(f"  Estrategia 2 (text): {len(tablas2)} tabla(s)")
                for ti, t in enumerate(tablas2, 1):
                    w(f"    Tabla {ti}: {len(t)} filas × {len(t[0]) if t else 0} columnas")
                    for fi, fila in enumerate(t[:10], 1):
                        cells = [str(c).strip().replace("\n", " ")[:30] if c else "" for c in fila]
                        w(f"      [{fi:>2}] " + " | ".join(cells))
                    if len(t) > 10:
                        w(f"      ... ({len(t) - 10} filas más)")

    texto = "\n".join(out)
    if salida:
        salida.write_text(texto, encoding="utf-8")
        print(f"Diagnóstico guardado en: {salida}  ({len(texto)} caracteres)")
    else:
        print(texto)
    return texto


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Ruta al PDF")
    parser.add_argument("--salida", type=Path, default=None, help="Guardar diagnóstico a archivo")
    args = parser.parse_args()
    if not args.pdf.is_file():
        sys.stderr.write(f"No existe el PDF: {args.pdf}\n")
        return 1
    diagnosticar(args.pdf, args.salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
