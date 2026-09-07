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

import zipfile
from io import BytesIO
from xml.sax.saxutils import escape as _xml_escape

from app.utils.moneda import parse_valor_cop as _parse_valor_cop

__all__ = [
    "generar_pdf_evidencia",
    "generar_zip_evidencias",
    "nombre_archivo_evidencia",
    "nombre_archivo_zip",
]


def _moneda(valor) -> str:
    """`$31.800`, igual que la macro (`TEXT(valor,"$#.##0")`)."""
    try:
        return "$" + f"{int(round(float(valor or 0))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "$0"


def _num(valor) -> float:
    """Un número, venga como venga.

    02-09-2026. La plata llega de la base como float, pero un dato traído de un
    Excel o de una macro puede llegar como texto («678.700»). Antes eso
    reventaba el PDF entero —`round()` sobre un str— y el gestor solo veía un
    error del servidor. Ahora se lee y, si de plano no es un número, es cero.
    """
    if isinstance(valor, (int, float)):
        return float(valor)
    return _parse_valor_cop(valor) if valor not in (None, "") else 0.0


def _esc(texto) -> str:
    return _xml_escape(str(texto or ""))


def rta_glosa_completa(glosa: dict) -> str:
    """La columna RTA GLOSA COMPLETA, con la misma fórmula de la macro.

    Se arma desde lo que el gestor decidió en la pantalla: si aceptó un valor,
    sale la variante con «CANTIDAD ACEPTADA»; si no, la de «POR VALOR DE».

    Si la glosa ya trae la respuesta escrita (`rta_completa`) —porque viene de
    la macro, donde la redactó el auditor— se usa **tal cual**: el texto del
    auditor no se vuelve a armar ni se corrige.
    """
    escrita = str(glosa.get("rta_completa") or "").strip()
    if escrita:
        return escrita
    causal = glosa.get("causal_codigo") or ""
    decision = glosa.get("decision") or ""
    descripcion = glosa.get("descripcion") or ""
    observacion = glosa.get("observacion_tecnico") or ""
    aceptado = _num(glosa.get("valor_aceptado"))
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


def nombre_archivo_zip(numero_paquete: str = "") -> str:
    """El nombre del ZIP con los PDF de todo el paquete."""
    limpio = "".join(c for c in str(numero_paquete or "") if c.isalnum())
    return f"RTA_ADRES_{('PAQ_' + limpio) if limpio else 'PAQUETE'}_EVIDENCIAS.zip"


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
        aceptado = _num(g.get("valor_aceptado"))
        filas.append(
            [
                Paragraph(_esc(datos.get("factura")), st_celda),
                Paragraph(_esc(int(round(_num(g.get("valor_glosado"))))), st_celda),
                Paragraph(_esc(datos.get("documento_paciente")), st_celda),
                Paragraph(_esc(g.get("descripcion")), st_celda),
                Paragraph(_esc(rta_glosa_completa(g)), st_celda),
                Paragraph(_moneda(aceptado) if aceptado else "", st_celda),
            ]
        )

    anchos = [2.4 * cm, 1.9 * cm, 2.6 * cm, 4.4 * cm, 5.4 * cm, 2.3 * cm]
    # `splitInRow` deja partir un renglón entre dos páginas. Hace falta: hay
    # respuestas de más de 2.500 caracteres —una sola celda más alta que la
    # hoja— y sin esto el PDF de esa factura no se puede armar.
    tabla = Table(filas, colWidths=anchos, repeatRows=1, splitInRow=1)
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

    try:
        doc.build(partes)
    except Exception:
        # 02-09-2026. Antes, si la maqueta de la tabla no cerraba, el gestor se
        # quedaba sin PDF y con un error del servidor. El papel es lo que
        # importa: se rehace en texto corrido, sin tabla, con la misma
        # información y avisando arriba por qué salió así.
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
        llanas = [
            Paragraph("REPORTE RTA ADRES", st_titulo),
            Paragraph(f"Número Factura: {_esc(datos.get('factura'))}", st_dato),
            Paragraph(f"Número Radicación: {_esc(datos.get('radicacion'))}", st_dato),
            Paragraph(f"Tip- Num Doc Victima: {_esc(datos.get('documento_paciente'))}", st_dato),
            Spacer(1, 0.4 * cm),
            Paragraph(
                "Este documento salió sin la tabla porque alguna respuesta es demasiado "
                "larga para la cuadrícula. La información es la misma.",
                st_pie,
            ),
            Spacer(1, 0.4 * cm),
        ]
        for i, g in enumerate(glosas, 1):
            aceptado = _num(g.get("valor_aceptado"))
            llanas.append(
                Paragraph(
                    f"<b>{i}. {_esc(g.get('descripcion'))}</b> — glosado "
                    f"{_moneda(g.get('valor_glosado'))}"
                    + (f" · aceptado {_moneda(aceptado)}" if aceptado else ""),
                    st_dato,
                )
            )
            llanas.append(Paragraph(_esc(rta_glosa_completa(g)), st_celda))
            llanas.append(Spacer(1, 0.25 * cm))
        for linea in pie:
            llanas.append(Paragraph(_esc(linea), st_pie))
        doc.build(llanas)
    return buffer.getvalue()


def generar_zip_evidencias(facturas: list[dict]) -> tuple[bytes, list[dict]]:
    """Un ZIP con el PDF de cada factura. Devuelve (zip, novedades).

    POR QUÉ EXISTE (02-09-2026). Yesid: «que salga una opción de descargar el
    PDF también de forma masiva y me quede en un zip con todas las facturas, un
    pdf por factura». Bajarlos de a uno con 81 facturas es un día de trabajo.

    Si una factura no se puede armar, **el ZIP igual sale**: esa factura queda
    anotada en `NOVEDADES.txt` dentro del mismo ZIP y en lo que se devuelve. Un
    error en una no puede dejar sin evidencia a las otras ochenta.
    """
    novedades: list[dict] = []
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        usados: set[str] = set()
        for posicion, datos in enumerate(facturas, 1):
            # Todo va dentro del try, incluido leer el número: si una entrada
            # viene corrupta, no puede tumbar el ZIP de las demás.
            numero = ""
            try:
                numero = str(datos.get("factura") or "")
                nombre = nombre_archivo_evidencia(numero)
                # Dos facturas no pueden pisarse dentro del ZIP.
                if nombre in usados:
                    raiz, _, ext = nombre.rpartition(".")
                    n = 2
                    while f"{raiz}_{n}.{ext}" in usados:
                        n += 1
                    nombre = f"{raiz}_{n}.{ext}"
                usados.add(nombre)
                zf.writestr(nombre, generar_pdf_evidencia(datos))
            except Exception as e:  # noqa: BLE001 — se anota y se sigue
                novedades.append(
                    {
                        "factura": numero or f"(la número {posicion} de la lista)",
                        "motivo": f"{type(e).__name__}: {e}",
                    }
                )
        if novedades:
            texto = [
                "NOVEDADES AL ARMAR LOS PDF DE EVIDENCIA",
                "",
                f"{len(novedades)} factura(s) no se pudieron armar. Las demás sí están en este ZIP.",
                "",
            ]
            texto += [f"{n['factura']}: {n['motivo']}" for n in novedades]
            zf.writestr("NOVEDADES.txt", "\n".join(texto).encode("utf-8"))
    return buffer.getvalue(), novedades
