"""PDF del oficio de devolución de pre-auditoría (DEV-PRE-AUD-####-AAAA).

Replica el formato del Excel de oficios que maneja el equipo:
encabezado con logo SINAC y consecutivo, tabla de facturas devueltas
(No., ENVÍO, FACTURA, F. FACTURA, VALOR, NIT, ENTIDAD, OFICIO, MOTIVO),
fila de TOTAL, nota de cierre y bloque de firmas (quien entrega por
Cartera/Pre-auditoría y quien recibe por Facturación).

Si existe `static/firma_preauditoria.png` se inserta como imagen de
firma sobre el nombre de quien entrega; si no, queda la línea para
firma manuscrita.
"""

from __future__ import annotations

import os
from io import BytesIO

from app.core.tz import ahora_bogota

RUTA_LOGO = os.path.join("static", "LOGO SINAC.png")
RUTA_FIRMA = os.path.join("static", "firma_preauditoria.png")

FIRMANTE_NOMBRE = "YUDY ALEXANDRA AMAYA GUTIERREZ"
FIRMANTE_CARGO = "Directora del proceso - Cartera"
FIRMANTE_EMPRESA = "Sinac Sc Sas - ESE Hospital Universitario de Santander"

RECIBE_NOMBRE = "ANGELICA LORENA POVEDA"
RECIBE_CARGO = "Coordinadora de Facturacion - Encargada"
RECIBE_EMPRESA = "Administracion en Salud CTA - ESE Hospital Universitario de Santander"

TITULO = (
    "ENTREGA DE NO ACEPTACIONES POR PRE AUDITORÍA PARA CORRECCIÓN "
    "POR PARTE DE FACTURACIÓN HUS"
)
SUBTITULO = "FACTURAS CON INCONVENIENTES DE LAS DIFERENTES E.R.P."

NOTA = (
    "NOTA: Se procedió a realizar la preauditoría de soportes de las facturas "
    "relacionadas, con el fin de contar con una facturación más viable para su "
    "pago. Agradecemos revisar las observaciones y realizar las respectivas "
    "correcciones para poder proceder con la radicación."
)


def _formatear_cop(valor: float) -> str:
    entero = f"{int(round(valor or 0)):,}".replace(",", ".")
    return f"$ {entero}"


def generar_pdf_oficio_devolucion(
    consecutivo: str,
    fecha_generado,
    numero_radicado: str,
    facturas: list[dict],
    generado_por: str = "",
) -> bytes:
    """Arma el PDF del oficio de devolución y devuelve los bytes.

    `facturas`: lista de dicts con envio, factura, fecha_factura, valor,
    nit, entidad y motivo_devolucion.
    """
    from reportlab.lib import colors
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    navy = HexColor("#0b3d91")
    gris = HexColor("#555555")

    st_titulo = ParagraphStyle(
        "titulo", fontName="Helvetica-Bold", fontSize=10.5, leading=13,
        alignment=TA_CENTER, textColor=navy,
    )
    st_sub = ParagraphStyle(
        "sub", fontName="Helvetica", fontSize=9, leading=11,
        alignment=TA_CENTER, textColor=gris,
    )
    st_meta = ParagraphStyle(
        "meta", fontName="Helvetica-Bold", fontSize=9.5, leading=12,
    )
    st_celda = ParagraphStyle("celda", fontName="Helvetica", fontSize=7.5, leading=9)
    st_celda_b = ParagraphStyle(
        "celda_b", fontName="Helvetica-Bold", fontSize=7.5, leading=9
    )
    st_nota = ParagraphStyle(
        "nota", fontName="Helvetica", fontSize=8.5, leading=11, alignment=TA_JUSTIFY,
    )
    st_firma = ParagraphStyle(
        "firma", fontName="Helvetica", fontSize=8.5, leading=11, alignment=TA_CENTER,
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=1.4 * cm,
        rightMargin=1.4 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"Oficio de devolución {consecutivo}",
        author="SINAC SC SAS - ESE Hospital Universitario de Santander",
    )
    ancho_util = doc.width
    story = []

    # --- Encabezado: logo + título + consecutivo/fecha -------------
    if os.path.exists(RUTA_LOGO):
        logo = Image(RUTA_LOGO, width=5.2 * cm, height=0.92 * cm)  # relación ~5.67:1
    else:
        logo = Paragraph("<b>SINAC SC SAS</b>", st_meta)
    fecha_txt = ""
    if fecha_generado is not None:
        fecha_txt = fecha_generado.strftime("%d/%m/%Y")
    meta = [
        Paragraph(f"Consecutivo: <b>{consecutivo}</b>", st_meta),
        Paragraph(f"Fecha: {fecha_txt}", st_meta),
        Paragraph(f"Oficio recibido: {numero_radicado or '—'}", st_meta),
    ]
    cab = Table(
        [[logo, [Paragraph(TITULO, st_titulo), Spacer(1, 2), Paragraph(SUBTITULO, st_sub)], meta]],
        colWidths=[5.6 * cm, ancho_util - 5.6 * cm - 6.2 * cm, 6.2 * cm],
    )
    cab.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.8, navy),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, navy),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(cab)
    story.append(Spacer(1, 10))

    # --- Tabla de facturas devueltas -------------------------------
    encabezados = [
        "No.", "ENVÍO", "FACTURA", "F. FACTURA", "VALOR", "NIT", "ENTIDAD", "MOTIVO DE LA DEVOLUCIÓN",
    ]
    filas = [[Paragraph(f"<b>{h}</b>", st_celda_b) for h in encabezados]]
    total = 0.0
    for i, f in enumerate(facturas, start=1):
        total += float(f.get("valor") or 0)
        ff = f.get("fecha_factura")
        ff_txt = ff.strftime("%d/%m/%Y") if ff else "—"
        filas.append(
            [
                Paragraph(str(i), st_celda),
                Paragraph(str(f.get("envio") or "—"), st_celda),
                Paragraph(str(f.get("factura") or "—"), st_celda),
                Paragraph(ff_txt, st_celda),
                Paragraph(_formatear_cop(f.get("valor") or 0), st_celda),
                Paragraph(str(f.get("nit") or "—"), st_celda),
                Paragraph(str(f.get("entidad") or "—"), st_celda),
                Paragraph(str(f.get("motivo_devolucion") or "—"), st_celda),
            ]
        )
    filas.append(
        [
            Paragraph(f"<b>TOTAL — {len(facturas)} factura(s)</b>", st_celda_b),
            "", "", "",
            Paragraph(f"<b>{_formatear_cop(total)}</b>", st_celda_b),
            "", "", "",
        ]
    )
    anchos = [
        0.9 * cm, 1.8 * cm, 3.0 * cm, 2.0 * cm, 2.2 * cm, 2.2 * cm, 4.6 * cm,
        ancho_util - (0.9 + 1.8 + 3.0 + 2.0 + 2.2 + 2.2 + 4.6) * cm,
    ]
    tabla = Table(filas, colWidths=anchos, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("SPAN", (0, -1), (3, -1)),
                ("SPAN", (5, -1), (7, -1)),
                ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#9db3d6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, HexColor("#eef3fb")]),
                ("BACKGROUND", (0, -1), (-1, -1), HexColor("#dce6f5")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(tabla)
    story.append(Spacer(1, 10))

    story.append(Paragraph(NOTA, st_nota))
    story.append(Spacer(1, 26))

    # --- Bloque de firmas ------------------------------------------
    def _bloque_firma(encima, nombre, cargo, empresa):
        """Tablita de un firmante: espacio/imagen de firma, línea y datos."""
        filas_firma = [
            [encima],
            [Paragraph(f"<b>{nombre}</b>", st_firma)],
            [Paragraph(cargo, st_firma)],
            [Paragraph(empresa, st_firma)],
        ]
        t = Table(filas_firma, colWidths=[9.5 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    # Línea de firma: solo sobre la fila del nombre.
                    ("LINEABOVE", (0, 1), (0, 1), 0.7, colors.black),
                    ("TOPPADDING", (0, 1), (0, 1), 5),
                    ("TOPPADDING", (0, 2), (0, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        return t

    if os.path.exists(RUTA_FIRMA):
        firma_entrega = Image(RUTA_FIRMA, width=4.2 * cm, height=1.6 * cm)
    else:
        firma_entrega = Spacer(1, 1.3 * cm)
    bloque_izq = _bloque_firma(
        firma_entrega, FIRMANTE_NOMBRE, FIRMANTE_CARGO, FIRMANTE_EMPRESA
    )
    bloque_der = [
        Paragraph("<b>RECIBIDO:</b>", st_firma),
        _bloque_firma(Spacer(1, 1.3 * cm), RECIBE_NOMBRE, RECIBE_CARGO, RECIBE_EMPRESA),
    ]
    t_firmas = Table(
        [[bloque_izq, bloque_der]],
        colWidths=[ancho_util / 2.0, ancho_util / 2.0],
    )
    t_firmas.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.append(t_firmas)

    st_pie = ParagraphStyle(
        "pie", fontName="Helvetica", fontSize=7, leading=9,
        alignment=TA_CENTER, textColor=gris,
    )
    generado = ahora_bogota().strftime("%d/%m/%Y %H:%M")
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            f"Documento generado por el módulo de Pre-auditoría SINAC el {generado}"
            + (f" · Elaborado por: {generado_por}" if generado_por else ""),
            st_pie,
        )
    )

    doc.build(story)
    return buf.getvalue()
