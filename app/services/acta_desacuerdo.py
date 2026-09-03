"""Acta de Desacuerdo: el documento que escala el caso a la Supersalud (V2, Pilar 5).

03-09-2026. Cuando la entidad ratifica su glosa y la IPS sostiene su respuesta,
el camino legal es la mesa de conciliación de auditoría médica y, si no hay
acuerdo, la Superintendencia Nacional de Salud (Arts. 57 y 126 de la Ley 1438
de 2011). Para ese escalamiento hace falta dejar POR ESCRITO la constancia del
desacuerdo: qué factura, qué glosa, qué sostiene cada parte y desde cuándo.

Ese formato se armaba a mano. Aquí el motor lo estructura solo, con los datos
REALES del expediente — y solo para glosas que de verdad están en etapa de
ratificación o conciliación: a una glosa inicial no se le fabrica un
desacuerdo que todavía no existe.

Reglas duras:
  - NO SE INVENTA NADA. Cada campo sale del registro; lo que no está, queda en
    blanco para que el auditor lo diligencie, y se le informa qué faltó.
  - Los espacios de firma quedan vacíos: el acta la firman personas.
  - Las actas que ya existían (acta SINAC, acta-Excel de la mesa) no se tocan:
    esas son el resultado DE la mesa; esta es la constancia que la EXIGE.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Optional

from app.core.logging_utils import logger

# Etapas que justifican un acta de desacuerdo. Una glosa inicial no la tiene.
_ETAPAS_CON_DESACUERDO = ("RATIFICACION", "CONCILIACION")

_CAMPOS_DEL_REGISTRO = (
    ("factura", "número de factura"),
    ("eps", "entidad responsable de pago"),
    ("codigo_glosa", "código de la glosa"),
    ("valor_objetado", "valor objetado"),
)


def _texto(v: Any) -> str:
    s = "" if v is None else str(v).strip()
    return "" if s.upper() == "N/A" else s


def _cop(v: Any) -> str:
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        return ""
    return "$" + f"{int(round(n)):,}".replace(",", ".") if n else ""


def etapa_procesal_de(glosa: Any) -> str:
    """La etapa del ciclo de vida de la glosa, leída del registro real.

    Reusa el clasificador del motor (PR #593): campo `etapa` + texto guardado.
    """
    from app.services.reglas_casos_fno import clasificar_etapa_procesal

    texto = (
        _texto(getattr(glosa, "texto_glosa_original", ""))
        or _texto(getattr(glosa, "observacion_eps", ""))
        or _texto(getattr(glosa, "dictamen", ""))
    )
    return clasificar_etapa_procesal(texto.upper(), _texto(getattr(glosa, "etapa", "")))


def exige_mesa(glosa: Any) -> bool:
    return etapa_procesal_de(glosa) in _ETAPAS_CON_DESACUERDO


def datos_acta_desacuerdo(glosa: Any) -> dict:
    """Los datos del acta, sacados del registro. Función pura: no inventa.

    Devuelve {campos..., "faltantes": [nombres legibles de lo que no está]}.
    """
    faltantes = []
    datos = {
        "factura": _texto(getattr(glosa, "factura", "")),
        "eps": _texto(getattr(glosa, "eps", "")),
        "codigo_glosa": _texto(getattr(glosa, "codigo_glosa", "")),
        "valor_objetado": _cop(getattr(glosa, "valor_objetado", 0)),
        "valor_aceptado": _cop(getattr(glosa, "valor_aceptado", 0)),
        "etapa_procesal": etapa_procesal_de(glosa),
        "numero_radicado": _texto(getattr(glosa, "numero_radicado", "")),
        "fecha_recepcion": "",
        "glosa_id": getattr(glosa, "id", None),
    }
    fr = getattr(glosa, "fecha_recepcion", None)
    if isinstance(fr, datetime):
        datos["fecha_recepcion"] = fr.strftime("%d/%m/%Y")
    for campo, nombre in _CAMPOS_DEL_REGISTRO:
        if not datos.get(campo):
            faltantes.append(nombre)
    datos["faltantes"] = faltantes
    return datos


def generar_pdf_acta_desacuerdo(datos: dict, hoy: Optional[datetime] = None) -> bytes:
    """El PDF del acta, sobrio y firmable. Mismo motor (reportlab) que el
    oficio de devolución. Los campos vacíos salen con línea para diligenciar."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    hoy = hoy or datetime.now()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="Acta de Desacuerdo",
    )
    azul = HexColor("#1e3a8a")
    gris = HexColor("#475569")
    st_titulo = ParagraphStyle(
        "t",
        fontSize=14,
        alignment=TA_CENTER,
        textColor=azul,
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    st_sub = ParagraphStyle("s", fontSize=9, alignment=TA_CENTER, textColor=gris, spaceAfter=10)
    st_h = ParagraphStyle(
        "h", fontSize=10, textColor=azul, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold"
    )
    st_p = ParagraphStyle("p", fontSize=9.5, alignment=TA_JUSTIFY, leading=13)

    def _o_linea(v: str) -> str:
        return v if v else "_________________________"

    partes = [
        Paragraph("ACTA DE DESACUERDO — GLOSA RATIFICADA", st_titulo),
        Paragraph(
            "E.S.E. HOSPITAL UNIVERSITARIO DE SANTANDER · Trámite de glosas, "
            "Arts. 57 y 126 de la Ley 1438 de 2011",
            st_sub,
        ),
        Paragraph("1. IDENTIFICACIÓN DEL CASO", st_h),
    ]
    tabla = Table(
        [
            ["Número de factura", _o_linea(datos.get("factura", ""))],
            ["Entidad responsable de pago", _o_linea(datos.get("eps", ""))],
            ["Código de glosa (Res. 2284/2023)", _o_linea(datos.get("codigo_glosa", ""))],
            ["Valor objetado", _o_linea(datos.get("valor_objetado", ""))],
            ["Valor aceptado por la IPS", datos.get("valor_aceptado", "") or "$0"],
            ["Radicado", _o_linea(datos.get("numero_radicado", ""))],
            ["Fecha de recepción de la glosa", _o_linea(datos.get("fecha_recepcion", ""))],
            ["Fecha del acta", hoy.strftime("%d/%m/%Y")],
        ],
        colWidths=[6.5 * cm, 10 * cm],
    )
    tabla.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), gris),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    partes += [
        tabla,
        Paragraph("2. CONSTANCIA DE DESACUERDO", st_h),
        Paragraph(
            "Agotado el trámite de respuesta previsto en el Artículo 57 de la Ley 1438 "
            "de 2011, la entidad responsable de pago RATIFICÓ la glosa identificada en "
            "este documento y la E.S.E. HOSPITAL UNIVERSITARIO DE SANTANDER SOSTIENE "
            "íntegramente la respuesta técnico-jurídica presentada en el trámite "
            "inicial, la cual hace parte del expediente. En consecuencia, las partes se "
            "encuentran en DESACUERDO sobre la procedencia de la objeción.",
            st_p,
        ),
        Paragraph("3. SOLICITUD DE MESA DE CONCILIACIÓN", st_h),
        Paragraph(
            "Con fundamento en el Artículo 57 de la Ley 1438 de 2011, se solicita la "
            "programación de la MESA DE CONCILIACIÓN DE AUDITORÍA MÉDICA Y/O TÉCNICA "
            "entre las partes para dirimir la controversia aquí documentada.",
            st_p,
        ),
        Paragraph("4. ESCALAMIENTO", st_h),
        Paragraph(
            "De no lograrse acuerdo en la mesa, el conflicto se elevará ante la "
            "SUPERINTENDENCIA NACIONAL DE SALUD, conforme al Artículo 126 de la Ley "
            "1438 de 2011 (función jurisdiccional y de conciliación), anexando la "
            "presente acta y el expediente completo de la glosa.",
            st_p,
        ),
        Spacer(1, 26),
    ]
    firmas = Table(
        [
            ["______________________________", "______________________________"],
            ["Por la E.S.E. HUS", "Por la entidad responsable de pago"],
            ["Nombre, cargo y fecha", "Nombre, cargo y fecha"],
        ],
        colWidths=[8.25 * cm, 8.25 * cm],
    )
    firmas.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TEXTCOLOR", (0, 1), (-1, -1), gris),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
            ]
        )
    )
    partes.append(firmas)
    if datos.get("faltantes"):
        partes += [
            Spacer(1, 14),
            Paragraph(
                "Nota interna (no hace parte del acta firmada): quedaron en blanco para "
                "diligenciar a mano: " + ", ".join(datos["faltantes"]) + ".",
                ParagraphStyle("n", fontSize=8, textColor=HexColor("#92400e")),
            ),
        ]

    doc.build(partes)
    pdf = buf.getvalue()
    logger.info(
        f"[ACTA-DESACUERDO] generada para factura {datos.get('factura') or 's/f'} "
        f"({len(pdf)} bytes, faltantes: {len(datos.get('faltantes') or [])})"
    )
    return pdf
