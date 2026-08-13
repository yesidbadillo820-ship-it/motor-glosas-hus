"""PDF de evidencia de una factura auditada del paquete ADRES.

Es el papel que queda cuando el gestor termina una factura: qué le glosó el
ADRES, qué se le respondió a cada glosa y cuánto se aceptó. Reproduce el
formato del `RTA_ADRES_HUS311371.pdf` que venía armando la macro — encabezado
con la factura, la radicación y el documento del paciente, y una tabla de seis
columnas:

    Número Factura | Valor Glosado | Tip- Num Doc Victima
    Descripción Elemento | RTA GLOSA COMPLETA | VALOR ACEPTADO

Las **glosas totales** (las que no traen causal propia porque el ADRES glosó la
reclamación entera por el FURIPS) no van en la tabla: no se responden una por
una. Se dicen en una nota al pie, para que el documento no oculte nada.
"""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape as _xml_escape

__all__ = ["generar_pdf_evidencia", "nombre_archivo_evidencia"]


def _moneda(valor) -> str:
    """`$31.800`, igual que la macro (`TEXT(valor,"$#.##0")`)."""
    try:
        return "$" + f"{int(round(float(valor or 0))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "$0"


def _esc(texto) -> str:
    return _xml_escape(str(texto or ""))


def rta_glosa_completa(glosa: dict) -> str:
    """La columna RTA GLOSA COMPLETA, con la misma fórmula de la macro.

    Se arma desde lo que el gestor decidió en la pantalla: si aceptó un valor,
    sale la variante con «CANTIDAD ACEPTADA»; si no, la de «POR VALOR DE».
    """
    causal = glosa.get("causal_codigo") or ""
    decision = glosa.get("decision") or ""
    descripcion = glosa.get("descripcion") or ""
    observacion = glosa.get("observacion_tecnico") or ""
    aceptado = glosa.get("valor_aceptado") or 0
    if aceptado > 0:
        cantidad = glosa.get("cantidad_aceptada") or ""
        return (
            f"{causal}-{decision} {descripcion}  CANTIDAD ACEPTADA {cantidad} . "
            f"POR VALOR {_moneda(aceptado)} {observacion}"
        )
    return (
        f"{causal}-{decision}-{descripcion}POR VALOR DE  "
        f"{_moneda(glosa.get('valor_glosado'))} {observacion}"
    )


def nombre_archivo_evidencia(factura: str) -> str:
    limpio = "".join(c for c in str(factura or "FACTURA") if c.isalnum() or c in "-_")
    return f"RTA_ADRES_{limpio or 'FACTURA'}.pdf"


def generar_pdf_evidencia(datos: dict) -> bytes:
    """Arma el PDF a partir de lo que devuelve `consultar_factura`."""
    from reportlab.lib import colors
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

    base = getSampleStyleSheet()
    st_titulo = ParagraphStyle(
        "TituloEvidencia", parent=base["Heading1"], fontSize=14, spaceAfter=10, leading=17
    )
    st_dato = ParagraphStyle("DatoEvidencia", parent=base["Normal"], fontSize=9.5, leading=14)
    st_cab = ParagraphStyle(
        "CabTabla", parent=base["Normal"], fontSize=8, leading=10, fontName="Helvetica-Bold"
    )
    st_celda = ParagraphStyle("CeldaTabla", parent=base["Normal"], fontSize=7.5, leading=9.5)
    st_pie = ParagraphStyle(
        "PieEvidencia", parent=base["Normal"], fontSize=7.5, leading=10, textColor=colors.grey
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"REPORTE RTA ADRES {datos.get('factura', '')}",
    )

    partes = [
        Paragraph("REPORTE RTA ADRES", st_titulo),
        Paragraph(f"Número Factura: {_esc(datos.get('factura'))}", st_dato),
        Paragraph(f"Número Radicación: {_esc(datos.get('radicacion'))}", st_dato),
        Paragraph(f"Tip- Num Doc Victima: {_esc(datos.get('documento_paciente'))}", st_dato),
        Spacer(1, 0.7 * cm),
    ]

    encabezados = [
        "Número Factura",
        "Valor Glosado",
        "Tip- Num Doc Victima",
        "Descripción Elemento",
        "RTA GLOSA COMPLETA",
        "VALOR ACEPTADO",
    ]
    filas = [[Paragraph(h, st_cab) for h in encabezados]]
    glosas = [g for g in datos.get("glosas", []) if not g.get("glosa_total")]
    for g in glosas:
        aceptado = g.get("valor_aceptado") or 0
        filas.append(
            [
                Paragraph(_esc(datos.get("factura")), st_celda),
                Paragraph(_esc(int(round(g.get("valor_glosado") or 0))), st_celda),
                Paragraph(_esc(datos.get("documento_paciente")), st_celda),
                Paragraph(_esc(g.get("descripcion")), st_celda),
                Paragraph(_esc(rta_glosa_completa(g)), st_celda),
                Paragraph(_moneda(aceptado) if aceptado else "", st_celda),
            ]
        )

    anchos = [2.4 * cm, 1.9 * cm, 2.6 * cm, 4.4 * cm, 5.4 * cm, 2.3 * cm]
    tabla = Table(filas, colWidths=anchos, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9D9D9")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    partes.append(tabla)

    resumen = datos.get("resumen", {}) or {}
    pie = [
        f"{len(glosas)} glosa(s) respondida(s) · glosado {_moneda(resumen.get('valor_glosado'))}"
        f" · aceptado {_moneda(resumen.get('valor_aceptado'))}."
    ]
    ocultas = resumen.get("glosas_totales_ocultas") or 0
    if ocultas:
        pie.append(
            f"No se incluyen {ocultas} renglón(es) de GLOSA TOTAL "
            f"({_moneda(resumen.get('valor_glosas_totales'))}): el ADRES glosó la reclamación "
            f"entera por el FURIPS y esos renglones no traen causal propia, "
            f"así que no se responden uno por uno."
        )
    pendientes = resumen.get("pendientes") or 0
    if pendientes:
        pie.append(f"ATENCIÓN: quedan {pendientes} glosa(s) sin decidir en esta factura.")

    partes.append(Spacer(1, 0.5 * cm))
    for linea in pie:
        partes.append(Paragraph(_esc(linea), st_pie))

    doc.build(partes)
    return buffer.getvalue()
