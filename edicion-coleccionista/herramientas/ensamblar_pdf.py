"""Ensambla la edición final: portada + fondo bajo todas las páginas.

Uso: python3 ensamblar_pdf.py libro.pdf portada.pdf fondo.pdf salida.pdf
(el libro debe estar compuesto al tamaño del fondo: 396.75 x 663 pt)
"""

import sys

from pypdf import PdfReader, PdfWriter

libro, portada, fondo, salida = sys.argv[1:5]
book = PdfReader(libro)
bg = PdfReader(fondo).pages[0]
cover = PdfReader(portada).pages[0]

w = PdfWriter()
w.add_page(cover)
for p in book.pages:
    p.merge_page(bg, over=False)
    w.add_page(p)
with open(salida, "wb") as f:
    w.write(f)
print(f"ok: {len(w.pages)} páginas -> {salida}")
