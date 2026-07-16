#!/usr/bin/env python3
"""Rasteriza páginas del PDF a PNG para revisión visual.
Uso: python3 src/rasterize.py <pdf> <dpi> [pág1 pág2 ...]   (1-indexadas; vacío=todas)
También crea un 'pliego' (contact sheet) con todas las páginas en miniatura."""

import sys, os, fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pdf = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(ROOT, "pdf", "HIJOS_DEL_FIRMAMENTO_Libro_I.pdf")
)
dpi = int(sys.argv[2]) if len(sys.argv) > 2 else 150
pages = [int(x) for x in sys.argv[3:]]
outdir = os.path.join(ROOT, "specimen", "paginas")
os.makedirs(outdir, exist_ok=True)
doc = fitz.open(pdf)
print("páginas totales:", doc.page_count)
sel = [p - 1 for p in pages] if pages else range(doc.page_count)
m = fitz.Matrix(dpi / 72, dpi / 72)
for i in sel:
    doc[i].get_pixmap(matrix=m).save(os.path.join(outdir, f"p{i + 1:03d}.png"))
print("render:", [i + 1 for i in sel])
