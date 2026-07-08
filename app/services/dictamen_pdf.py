"""PDF radicable de la respuesta de glosa (documento formal).

Varias EPS exigen subir un PDF con la respuesta del hospital para
radicar la objeción en sus portales. Este servicio convierte el
dictamen (que se guarda como HTML) en un documento formal:

  - Encabezado institucional: ESE HOSPITAL UNIVERSITARIO DE SANTANDER
    + "RESPUESTA A GLOSA / OBJECIÓN" + fecha en hora de Colombia
    (America/Bogota — nunca datetime.now() naive).
  - Bloque de datos: entidad, factura, código glosa, valor objetado
    (formato COP), código respuesta, paciente si existe.
  - Cuerpo: la tabla de cabecera del dictamen se reconstruye como
    Table de reportlab; el resto del HTML pasa a párrafos limpios vía
    app/utils/html_a_texto (sin tags crudos).
  - Pie: aviso "Generado por IA GLOSAS SINAC SC — verificar antes de
    radicar" + espacio para firma y sello.

Distinto de app/api/routers/dictamen_pdf.py (PDF interno con hash de
integridad): este es el documento que se RADICA ante la entidad.
"""

from io import BytesIO
from xml.sax.saxutils import escape as _xml_escape

from app.core.tz import ahora_bogota
from app.utils.html_a_texto import dictamen_a_texto_plano, extraer_tabla_cabecera

_MESES_ES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def _fecha_larga_bogota() -> str:
    """'Bucaramanga, 10 de junio de 2026' en hora de Colombia."""
    hoy = ahora_bogota()
    return f"Bucaramanga, {hoy.day} de {_MESES_ES[hoy.month - 1]} de {hoy.year}"


def formatear_cop(valor) -> str:
    """Float/None → '$ 36.402' (separador de miles colombiano)."""
    try:
        n = float(valor or 0)
    except (TypeError, ValueError):
        n = 0.0
    return "$ " + f"{n:,.0f}".replace(",", ".")


def _esc(texto) -> str:
    """Escapa texto para el mini-markup XML de Paragraph de reportlab."""
    return _xml_escape(str(texto or ""))


def _parrafo_multilinea(texto: str) -> str:
    """Texto plano con \\n → markup de Paragraph con <br/>."""
    return _esc(texto).replace("\n", "<br/>")


def generar_pdf_dictamen(glosa) -> bytes:
    """Genera el PDF radicable de la respuesta de UNA glosa.

    Args:
        glosa: GlosaRecord con dictamen no vacío.

    Returns:
        bytes del PDF (empiezan con %PDF).

    Raises:
        ValueError: si la glosa no tiene dictamen registrado.
    """
    if not (getattr(glosa, "dictamen", None) or "").strip():
        raise ValueError("La glosa no tiene dictamen registrado — nada que radicar")

    from reportlab.lib import colors
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    NAVY = HexColor("#0b3d91")
    INK = HexColor("#0b1220")
    GRAY = HexColor("#334155")
    GRAY_LIGHT = HexColor("#94a3b8")
    BG = HexColor("#f5f7fa")

    styles = getSampleStyleSheet()
    st_titulo = ParagraphStyle(
        "TituloHUS",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=INK,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    st_subtitulo = ParagraphStyle(
        "SubtituloHUS",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=NAVY,
        alignment=TA_CENTER,
        spaceBefore=4,
        spaceAfter=2,
    )
    st_fecha = ParagraphStyle(
        "FechaHUS",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=GRAY,
        alignment=TA_CENTER,
    )
    st_seccion = ParagraphStyle(
        "SeccionHUS",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=NAVY,
        spaceBefore=12,
        spaceAfter=4,
    )
    st_cuerpo = ParagraphStyle(
        "CuerpoHUS",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=GRAY,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    st_celda = ParagraphStyle(
        "CeldaHUS",
        parent=st_cuerpo,
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        spaceAfter=0,
    )
    st_pie = ParagraphStyle(
        "PieHUS",
        parent=styles["BodyText"],
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        leading=10,
        textColor=GRAY_LIGHT,
        alignment=TA_CENTER,
    )

    factura = getattr(glosa, "factura", None) or f"#{getattr(glosa, 'id', '')}"
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2.0 * cm,
        title=f"Respuesta a glosa — Factura {factura}",
        author="ESE Hospital Universitario de Santander",
    )

    linea = Table([[""]], colWidths=[doc.width])
    linea.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, NAVY),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    story: list = []

    # ── Encabezado institucional ────────────────────────────────────
    story.append(Paragraph("ESE HOSPITAL UNIVERSITARIO DE SANTANDER", st_titulo))
    story.append(Paragraph("NIT 900.006.037-4 · Bucaramanga, Santander", st_fecha))
    story.append(Paragraph("RESPUESTA A GLOSA / OBJECIÓN", st_subtitulo))
    story.append(Paragraph(_esc(_fecha_larga_bogota()), st_fecha))
    story.append(Spacer(1, 8))
    story.append(linea)
    story.append(Spacer(1, 12))

    # ── Bloque de datos de la glosa ─────────────────────────────────
    try:
        from app.services.resolver_entidad import resolver_entidad_mostrar

        entidad = resolver_entidad_mostrar(
            eps=getattr(glosa, "eps", None),
            tercero_nombre=getattr(glosa, "tercero_nombre", None),
            eps_codigo=getattr(glosa, "eps_codigo", None),
        )
    except Exception:
        entidad = getattr(glosa, "eps", None) or "—"

    datos = [
        ["EPS / Entidad", entidad[:90]],
        ["Factura", factura],
        ["Código glosa", getattr(glosa, "codigo_glosa", None) or "—"],
        ["Valor objetado", formatear_cop(getattr(glosa, "valor_objetado", 0))],
        ["Código respuesta", getattr(glosa, "codigo_respuesta", None) or "—"],
    ]
    paciente = getattr(glosa, "paciente", None)
    if paciente:
        datos.append(["Paciente", str(paciente)[:90]])
    numero_radicado = getattr(glosa, "numero_radicado", None)
    if numero_radicado:
        datos.append(["N° Radicado", str(numero_radicado)[:50]])

    t_datos = Table(
        [[k, _esc(v)] for k, v in datos],
        colWidths=[4.2 * cm, doc.width - 4.2 * cm],
    )
    t_datos.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), GRAY),
                ("BACKGROUND", (0, 0), (0, -1), BG),
                ("GRID", (0, 0), (-1, -1), 0.4, GRAY_LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t_datos)
    story.append(Spacer(1, 14))

    # ── Cuerpo: dictamen (HTML → tabla reportlab + párrafos) ────────
    filas_cabecera, html_resto = extraer_tabla_cabecera(glosa.dictamen or "")
    if filas_cabecera:
        n_cols = max(len(f) for f in filas_cabecera)

        def _fila_pdf(fila: list, es_encabezado: bool) -> list:
            celdas = [
                Paragraph(
                    f"<font color='white'><b>{_esc(c)}</b></font>" if es_encabezado else _esc(c),
                    st_celda,
                )
                for c in fila
            ]
            # Filas con menos celdas (trazabilidad colspan=3) → rellenar
            celdas += [Paragraph("", st_celda)] * (n_cols - len(celdas))
            return celdas

        filas_pdf = [_fila_pdf(f, es_encabezado=(i == 0)) for i, f in enumerate(filas_cabecera)]
        t_cab = Table(filas_pdf, colWidths=[doc.width / n_cols] * n_cols)
        t_cab.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, GRAY_LIGHT),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ]
            )
        )
        story.append(t_cab)
        story.append(Spacer(1, 10))

    story.append(Paragraph("RESPUESTA DEL HOSPITAL", st_seccion))
    texto_dictamen = dictamen_a_texto_plano(html_resto)
    if not texto_dictamen:
        texto_dictamen = dictamen_a_texto_plano(glosa.dictamen)
    for parrafo in texto_dictamen.split("\n\n"):
        if parrafo.strip():
            story.append(Paragraph(_parrafo_multilinea(parrafo.strip()), st_cuerpo))

    # ── Espacio de firma y sello ────────────────────────────────────
    story.append(Spacer(1, 34))
    t_firma = Table(
        [
            ["", ""],
            ["Firma y sello — ESE HUS", "Fecha de radicación ante la entidad"],
        ],
        colWidths=[doc.width / 2.0] * 2,
    )
    t_firma.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 1), (0, 1), 0.7, colors.black),
                ("LINEABOVE", (1, 1), (1, 1), 0.7, colors.black),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, 1), 8),
                ("TEXTCOLOR", (0, 1), (-1, 1), GRAY),
                ("TOPPADDING", (0, 0), (-1, 0), 24),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 24),
            ]
        )
    )
    story.append(t_firma)

    # ── Pie ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(linea)
    story.append(Spacer(1, 5))
    story.append(
        Paragraph(
            "Generado por IA GLOSAS SINAC SC — verificar antes de radicar.",
            st_pie,
        )
    )
    story.append(
        Paragraph(
            f"Glosa interna #{getattr(glosa, 'id', '—')} · Documento generado el "
            f"{ahora_bogota().strftime('%d/%m/%Y %H:%M')} hora Colombia.",
            st_pie,
        )
    )

    doc.build(story)
    return buf.getvalue()


def nombre_archivo_pdf(glosa) -> str:
    """`respuesta_glosa_{factura}_{id}.pdf` saneado para Content-Disposition."""
    import re

    factura = str(getattr(glosa, "factura", "") or "SIN-FACTURA")
    factura = re.sub(r"[^A-Za-z0-9_\-]", "-", factura).strip("-") or "SIN-FACTURA"
    return f"respuesta_glosa_{factura}_{getattr(glosa, 'id', 0)}.pdf"
