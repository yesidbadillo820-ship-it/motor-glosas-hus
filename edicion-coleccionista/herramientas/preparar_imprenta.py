"""Prepara los archivos de imprenta de la Edición Coleccionista.

Genera:
  1. Interior con sangrado de 3 mm (fondo extendido al corte, texto en posición).
  2. Carátula extendida: contraportada + lomo + portada, con sangrado.

Uso:
  python3 preparar_imprenta.py <interior_sin_fondo.pdf> <portada.pdf> <fondo.pdf> \
      <salida_interior.pdf> <salida_caratula.pdf> [lomo_mm]

El interior debe estar compuesto al tamaño de corte (396.75 x 663 pt = 14.0 x 23.4 cm).
El lomo por defecto es 10 mm (~178 páginas en bond 90 g); ajústelo al dato de la imprenta.
"""

import sys

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

MM = 72 / 25.4
BLEED = 3 * MM
TRIM_W, TRIM_H = 396.75, 663.0

FUENTES = "/usr/share/fonts/truetype/liberation"
pdfmetrics.registerFont(TTFont("Serif", f"{FUENTES}/LiberationSerif-Regular.ttf"))
pdfmetrics.registerFont(TTFont("SerifIt", f"{FUENTES}/LiberationSerif-Italic.ttf"))
pdfmetrics.registerFont(TTFont("SerifB", f"{FUENTES}/LiberationSerif-Bold.ttf"))
# Liberation Serif no trae el glifo ✦ (U+2726); DejaVu Sans sí
pdfmetrics.registerFont(TTFont("Orn", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))


def interior_con_sangrado(interior_pdf, fondo_pdf, salida):
    book = PdfReader(interior_pdf)
    fondo = PdfReader(fondo_pdf).pages[0]
    w, h = TRIM_W + 2 * BLEED, TRIM_H + 2 * BLEED
    s = max(w / TRIM_W, h / TRIM_H)
    bx, by = (w - TRIM_W * s) / 2, (h - TRIM_H * s) / 2
    out = PdfWriter()
    for p in book.pages:
        np = out.add_blank_page(width=w, height=h)
        np.merge_transformed_page(fondo, Transformation().scale(s).translate(bx, by))
        np.merge_transformed_page(p, Transformation().translate(BLEED, BLEED))
        np.trimbox = RectangleObject([BLEED, BLEED, BLEED + TRIM_W, BLEED + TRIM_H])
    with open(salida, "wb") as f:
        out.write(f)
    print(f"interior: {len(out.pages)} páginas -> {salida}")


def overlay_caratula(ancho, alto, lomo_x, lomo_w, tmp):
    c = canvas.Canvas(tmp, pagesize=(ancho, alto))
    # lomo
    c.setFillColor(HexColor("#241729"))
    c.rect(lomo_x, 0, lomo_w, alto, stroke=0, fill=1)
    c.setFillColor(HexColor("#c9a959"))
    c.saveState()
    c.translate(lomo_x + lomo_w / 2, alto / 2)
    c.rotate(-90)
    c.setFont("Serif", 12.5)
    c.drawCentredString(0, -4.3, "HIJOS DEL FIRMAMENTO   ·   YESID BADILLO")
    c.restoreState()
    # contraportada
    cx = BLEED + TRIM_W / 2
    sepia, oro = HexColor("#41321f"), HexColor("#7a5c2e")
    y = alto - BLEED - 150
    c.setFillColor(oro)
    c.setFont("Orn", 13)
    c.drawCentredString(cx, y, "✦")
    y -= 56
    c.setFillColor(sepia)
    c.setFont("SerifIt", 16.5)
    c.drawCentredString(cx, y, "—Cuando te mueras,")
    y -= 26
    c.drawCentredString(cx, y, "¿cuánto tiempo te voy a seguir viendo?")
    y -= 70
    c.setFont("SerifIt", 12)
    for linea in (
        "Una épica de grandes almas, mitología viva",
        "y el amor que lo recuerda todo.",
    ):
        c.drawCentredString(cx, y, linea)
        y -= 20
    y -= 46
    c.setFillColor(oro)
    c.setFont("Orn", 13)
    c.drawCentredString(cx, y, "✦")
    c.setFillColor(sepia)
    c.setFont("Serif", 13)
    c.drawCentredString(cx, BLEED + 96, "YESID PÉREZ BADILLO")
    c.setFont("Serif", 9.5)
    c.drawCentredString(cx, BLEED + 78, "EDICIÓN COLECCIONISTA")
    c.save()


def caratula_extendida(portada_pdf, fondo_pdf, salida, lomo_mm):
    lomo = lomo_mm * MM
    ancho = 2 * BLEED + 2 * TRIM_W + lomo
    alto = TRIM_H + 2 * BLEED
    panel = TRIM_W + BLEED
    s = max(panel / TRIM_W, alto / TRIM_H)

    fondo = PdfReader(fondo_pdf).pages[0]
    portada = PdfReader(portada_pdf).pages[0]
    out = PdfWriter()
    pg = out.add_blank_page(width=ancho, height=alto)
    # contraportada (anclada al lomo, rebasa hacia el corte izquierdo)
    tx = (BLEED + TRIM_W) - TRIM_W * s
    ty = (alto - TRIM_H * s) / 2
    pg.merge_transformed_page(fondo, Transformation().scale(s).translate(tx, ty))
    # portada (anclada al lomo, rebasa hacia el corte derecho)
    fx = BLEED + TRIM_W + lomo
    pg.merge_transformed_page(portada, Transformation().scale(s).translate(fx, ty))
    # lomo + textos
    tmp = salida + ".overlay.tmp"
    overlay_caratula(ancho, alto, BLEED + TRIM_W, lomo, tmp)
    pg.merge_page(PdfReader(tmp).pages[0])
    pg.trimbox = RectangleObject([BLEED, BLEED, ancho - BLEED, alto - BLEED])
    with open(salida, "wb") as f:
        out.write(f)
    print(f"carátula: {ancho / MM:.1f} x {alto / MM:.1f} mm (lomo {lomo_mm} mm) -> {salida}")


if __name__ == "__main__":
    interior, portada, fondo, out_int, out_car = sys.argv[1:6]
    lomo_mm = float(sys.argv[6]) if len(sys.argv) > 6 else 10.0
    interior_con_sangrado(interior, fondo, out_int)
    caratula_extendida(portada, fondo, out_car, lomo_mm)
