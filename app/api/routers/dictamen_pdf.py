"""PDF profesional del dictamen.

Genera PDF con membrete institucional HUS, tipografia premium, tabla
de identificacion, secciones formateadas y hash SHA-256 de
integridad. Listo para firmar/enviar a la EPS sin pasar por Word.
"""
from __future__ import annotations
import hashlib
import io
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord


router = APIRouter(prefix="/dictamen-pdf", tags=["dictamen-pdf"])


def _strip_html(text: str) -> str:
    """Quita tags HTML preservando saltos de linea y espacios."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "  • ", text, flags=re.I)
    text = re.sub(r"</?h[1-6][^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    # Decodear entities basicos
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&aacute;", "á")
    text = text.replace("&eacute;", "é").replace("&iacute;", "í")
    text = text.replace("&oacute;", "ó").replace("&uacute;", "ú")
    text = text.replace("&ntilde;", "ñ").replace("&Ntilde;", "Ñ")
    # Colapsar espacios multiples y saltos triples+
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@router.get("/{glosa_id}")
def descargar_pdf_dictamen(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Genera y descarga PDF profesional del dictamen de la glosa.

    Estructura:
        - Cabecera: HUS NIT 900.006.037-4 + linea separadora navy
        - Tabla identificacion (factura, EPS, fecha, valor objetado)
        - Texto de la glosa original
        - Dictamen formateado en parrafos
        - Pie: hash SHA-256 + timestamp + gestor responsable
    """
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(404, "Glosa no encontrada")

    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
    from reportlab.lib.units import cm, inch
    from reportlab.lib.colors import HexColor, black
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, KeepTogether,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.5 * cm, bottomMargin=2.0 * cm,
        title=f"Dictamen {g.factura or '#'+str(g.id)}",
        author="ESE HUS",
    )

    styles = getSampleStyleSheet()
    NAVY = HexColor("#0b3d91")
    NAVY_DARK = HexColor("#0b1220")
    GRAY_TEXT = HexColor("#334155")
    GRAY_LIGHT = HexColor("#94a3b8")
    BG_TABLE = HexColor("#f5f7fa")

    h1 = ParagraphStyle(
        "H1", parent=styles["Title"],
        fontName="Helvetica-Bold", fontSize=14, leading=18,
        textColor=NAVY_DARK, alignment=TA_CENTER, spaceAfter=4,
    )
    h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontName="Helvetica-Bold", fontSize=10.5, leading=14,
        textColor=NAVY, spaceBefore=10, spaceAfter=4,
    )
    body = ParagraphStyle(
        "Body", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=9.5, leading=14,
        textColor=GRAY_TEXT, alignment=TA_JUSTIFY, spaceAfter=6,
    )
    small = ParagraphStyle(
        "Small", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=7.5, leading=10,
        textColor=GRAY_LIGHT, alignment=TA_CENTER,
    )
    foot = ParagraphStyle(
        "Foot", parent=styles["BodyText"],
        fontName="Helvetica-Oblique", fontSize=7, leading=9.5,
        textColor=GRAY_LIGHT, alignment=TA_CENTER,
    )

    story: list = []

    # Cabecera institucional
    story.append(Paragraph(
        "<b>ESE HOSPITAL UNIVERSITARIO DE SANTANDER</b>",
        h1
    ))
    story.append(Paragraph(
        "NIT 900.006.037-4 · Bucaramanga, Santander · Colombia",
        small
    ))
    story.append(Spacer(1, 8))
    # Linea separadora
    line_t = Table([[" "]], colWidths=[doc.width])
    line_t.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 1.5, NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(line_t)
    story.append(Spacer(1, 12))

    # Titulo principal
    story.append(Paragraph(
        f"<b>DICTAMEN DE GLOSA</b> &nbsp; · &nbsp; Factura {g.factura or '#'+str(g.id)}",
        h1,
    ))
    story.append(Spacer(1, 14))

    # Tabla de identificacion
    fecha_str = g.creado_en.strftime("%d/%m/%Y") if g.creado_en else "—"
    valor_obj = f"$ {(g.valor_objetado or 0):,.0f}".replace(",", ".")
    valor_acep = f"$ {(g.valor_aceptado or 0):,.0f}".replace(",", ".")
    info_data = [
        ["Factura", g.factura or "—", "Fecha glosa", fecha_str],
        ["EPS / Pagador", (g.eps or "—")[:60], "Código glosa", g.codigo_glosa or "—"],
        ["Valor objetado", valor_obj, "Valor aceptado", valor_acep],
        ["Etapa", g.etapa or "—", "Estado", g.estado or "—"],
    ]
    info_t = Table(info_data, colWidths=[3.0 * cm, 5.5 * cm, 3.0 * cm, 5.5 * cm])
    info_t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, -1), GRAY_TEXT),
        ("BACKGROUND", (0, 0), (0, -1), BG_TABLE),
        ("BACKGROUND", (2, 0), (2, -1), BG_TABLE),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, GRAY_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(info_t)
    story.append(Spacer(1, 14))

    # Glosa original (texto del pagador)
    if g.texto_glosa_original:
        story.append(Paragraph("1. GLOSA OBJETADA POR EL PAGADOR", h2))
        story.append(Paragraph(
            _strip_html(g.texto_glosa_original).replace("\n", "<br/>"),
            body,
        ))

    # Concepto / motivo
    if g.concepto_glosa:
        story.append(Paragraph("2. CONCEPTO DE LA GLOSA", h2))
        story.append(Paragraph(_strip_html(g.concepto_glosa), body))

    # Dictamen / argumentacion
    story.append(Paragraph("3. ARGUMENTACIÓN JURÍDICA Y TÉCNICA", h2))
    dictamen_clean = _strip_html(g.dictamen or "Sin dictamen registrado")
    # Dividir por parrafos dobles
    for parrafo in dictamen_clean.split("\n\n"):
        if parrafo.strip():
            story.append(Paragraph(
                parrafo.replace("\n", "<br/>"),
                body,
            ))

    # Decision EPS si ya hubo
    if g.decision_eps:
        story.append(Paragraph("4. DECISIÓN DEL PAGADOR", h2))
        valor_rec = f"$ {(g.valor_recuperado or 0):,.0f}".replace(",", ".")
        decision_text = f"<b>{g.decision_eps}</b>"
        if g.fecha_decision_eps:
            decision_text += f" · Fecha: {g.fecha_decision_eps.strftime('%d/%m/%Y')}"
        if g.valor_recuperado:
            decision_text += f" · Valor recuperado: {valor_rec}"
        if g.observacion_eps:
            decision_text += f"<br/><i>{_strip_html(g.observacion_eps)[:500]}</i>"
        story.append(Paragraph(decision_text, body))

    # Footer con hash de integridad
    contenido_hash = (g.dictamen or "") + str(g.id) + str(g.creado_en or "") + (g.factura or "")
    sha = hashlib.sha256(contenido_hash.encode("utf-8")).hexdigest()
    story.append(Spacer(1, 20))
    story.append(line_t)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>Documento generado:</b> {ahora_utc().strftime('%d/%m/%Y %H:%M')} UTC · "
        f"<b>Gestor responsable:</b> {current_user.nombre or current_user.email}",
        foot,
    ))
    story.append(Paragraph(
        f"<b>Hash de integridad:</b> <font face='Courier'>{sha[:32]}...{sha[-8:]}</font>",
        foot,
    ))
    story.append(Paragraph(
        "Este documento es generado automáticamente por el Motor de Glosas HUS. "
        "El hash SHA-256 garantiza la integridad del dictamen al momento de generación.",
        foot,
    ))

    # Construir
    doc.build(story)
    buf.seek(0)

    fname = f"dictamen-{g.factura or g.id}-{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
