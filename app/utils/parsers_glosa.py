"""Parsers y helpers de glosas (Ronda 50 Paso 9 — extraído de main.py).

Contiene:
  - _detectar_servicio_desde_texto(): heurística para extraer el nombre
    del servicio clínico del texto de la glosa.
  - _extraer_motivo_glosa(): extrae la razón humana de la objeción.
  - _concepto_glosa(): mapeo código → concepto canónico Res. 2284/2023.
  - _extraer_valores_glosa(): facturado/objetado/reconocido del texto.
  - _generar_banner_tarifa_html(): banner HTML cuando hay tarifa match.
  - _extraer_cups_servicio(): CUPS + descripción desde el texto (acepta
    códigos HUS con sufijos H/H1/-18/-16).
  - _descripcion_servicio(): descripción fallback por prefijo TA/SO/AU.

Estos helpers son usados por app.main y otros módulos (glosa_service,
ia_auditora_proactiva) para no duplicar lógica de parsing.
"""
from __future__ import annotations

import re
from typing import Optional

def _detectar_servicio_desde_texto(texto_glosa: str, contexto_pdf: str = "") -> Optional[str]:
    """Intenta extraer el nombre del servicio/procedimiento y el CUPS desde el texto
    de la glosa y/o los soportes adjuntos.

    Retorna una cadena tipo "ESTUDIO DE COLORACIÓN BÁSICA EN BIOPSIA (CUPS 898040)"
    cuando puede identificarlo; None en caso contrario.
    """
    if not texto_glosa and not contexto_pdf:
        return None
    fuente = f"{texto_glosa}\n{contexto_pdf}".upper()

    # 1. Buscar CUPS (código numérico de 5-6 dígitos)
    cups_match = re.search(r"\b(\d{5,6})\b", fuente)
    cups = cups_match.group(1) if cups_match else None

    # 2. Buscar una descripción de servicio después de palabras clave comunes
    desc = None
    patrones = [
        # Servicio explícito con etiqueta previa
        r"(?:SERVICIO|PROCEDIMIENTO|DESCRIPCI[ÓO]N\s+DEL\s+SERVICIO|ACTIVIDAD)\s*[:\-]\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,\-/]{5,70})",
        # Menciones clínicas típicas (cortadas antes de signos de puntuación o fin de oración)
        r"\b(CONSULTA\s+(?:DE|EN|EXTERNA|CONTROL|URGENCIA|ESPECIALIZADA)[A-ZÁÉÍÓÚÑ ,\-]{0,50})",
        r"\b(CIRUG[ÍI]A\s+(?:DE|POR|LAPAROSC[ÓO]PICA|ABIERTA)[A-ZÁÉÍÓÚÑ ,\-]{0,50})",
        r"\b(ESTUDIO\s+(?:DE|DEL|POR|EN)[A-ZÁÉÍÓÚÑ ,\-]{5,60})",
        r"\b(TOMOGRAF[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,50})",
        r"\b(RESONANCIA\s+[A-ZÁÉÍÓÚÑ ,\-]{3,50})",
        r"\b(ECOGRAF[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,50})",
        r"\b(BIOPSIA\s+[A-ZÁÉÍÓÚÑ ,\-]{0,50})",
        r"\b(RADIOGRAF[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,50})",
        r"\b(HEMOGRAMA[A-ZÁÉÍÓÚÑ ,\-]{0,40})",
        r"\b(HOSPITALIZACI[ÓO]N\s+[A-ZÁÉÍÓÚÑ ,\-]{0,50})",
        r"\b(CRANEOTOM[ÍI]A[A-ZÁÉÍÓÚÑ ,\-]{0,60})",
        r"\b(APENDICECTOM[ÍI]A[A-ZÁÉÍÓÚÑ ,\-]{0,40})",
        r"\b(COLECISTECTOM[ÍI]A[A-ZÁÉÍÓÚÑ ,\-]{0,40})",
    ]
    for pat in patrones:
        m = re.search(pat, fuente)
        if m:
            desc = (m.group(1) if m.groups() else m.group(0)).strip()
            # Cortar en separadores que indican fin natural de la descripción
            desc = re.split(r"\s+(?:COBRO|DIFERENCIA|VALOR|SIN|CON|POR\s+VALOR|MOTIVO|OBSERVACI)", desc)[0]
            desc = re.sub(r"\s+", " ", desc).strip().rstrip(",-.")
            if 5 <= len(desc) <= 80:
                break
            desc = None

    if desc and cups:
        return f"{desc} (CUPS {cups})"
    if desc:
        return desc
    if cups:
        return f"CUPS {cups}"
    return None


# Concepto oficial (Anexo Técnico 6 Res. 3047/2008) por código de glosa.
# Se usa mostrar en la tabla de historial. Si no hay match exacto, se usa el
# concepto por prefijo.
CONCEPTOS_CODIGOS: dict[str, str] = {
    # Tarifa (TA)
    "TA01": "Los cargos por consulta, interconsulta o atención (visita) domiciliaria, presentan diferencias con los valores pactados o establecidos por la norma",
    "TA02": "Los cargos por estancia presentan diferencias con los valores pactados o establecidos por la norma",
    "TA03": "Los cargos por honorarios (médicos o quirúrgicos) presentan diferencias con los valores pactados o establecidos por la norma",
    "TA04": "Los cargos por derechos de sala presentan diferencias con los valores pactados o establecidos por la norma",
    "TA05": "Los cargos por materiales presentan diferencias con los valores pactados o establecidos por la norma",
    "TA06": "Los cargos por medicamentos o APME presentan diferencias con los valores pactados o establecidos por la norma",
    "TA07": "Los cargos por medicamentos o APME que vienen relacionados o justificados en los soportes de cobro, presentan diferencias con los valores pactados o establecidos por la norma",
    "TA08": "Los cargos por procedimientos quirúrgicos o no quirúrgicos presentan diferencias con los valores pactados o establecidos por la norma",
    "TA09": "Los cargos por apoyo diagnóstico terapéutico presentan diferencias con los valores pactados o establecidos por la norma",
    # Soportes (SO)
    "SO01": "Faltan soportes de la atención, historia clínica o documentación exigida",
    "SO02": "Los soportes presentan inconsistencias o están incompletos",
    "SO42": "Lista de precios no aportada o insuficiente",
    # Autorización (AU)
    "AU01": "Servicio prestado sin autorización previa",
    "AU02": "Diferencia con el servicio autorizado",
    # Cobertura (CO)
    "CO01": "Servicio no incluido en el PBS o régimen aplicable",
    "CO02": "Servicio no cubierto por régimen especial",
    "CO03": "Servicio no incluido en el PBS del régimen subsidiado o contributivo",
    # Pertinencia (CL / PE)
    "CL01": "Procedimiento no pertinente según criterio clínico",
    "PE01": "Procedimiento no pertinente según criterio clínico",
    # Facturación (FA)
    "FA01": "Error formal en la facturación (código, fecha, firma)",
    "FA02": "Error en código CUPS o código no corresponde",
    # Insumos (IN)
    "IN01": "Insumos no reconocidos o no pactados",
    "IN02": "Diferencia en valor de insumos",
    # Medicamentos (ME)
    "ME01": "Medicamento no incluido en PBS o fuera de cobertura",
    "ME02": "Medicamento no justificado por fórmula médica",
}


def _extraer_motivo_glosa(texto: str) -> str:
    """Extrae solo el motivo/observación de la glosa, quitando código, concepto,
    CUPS, servicio y valores numéricos (que ya están en columnas separadas).

    Formato típico del Excel:
      CODIGO - CONCEPTO - CUPS - SERVICIO - VALOR_OBJ - MOTIVO - VALOR_ACEP
    Devuelve el último segmento TEXTUAL que no sea un código ni un valor.
    Si no logra identificarlo, devuelve el texto original.
    """
    if not texto:
        return ""
    t = texto.strip()
    partes = [p.strip() for p in t.split(" - ")]
    if len(partes) <= 2:
        return t

    def _es_descartable(p: str) -> bool:
        if not p:
            return True
        # Valor monetario o numérico puro (solo dígitos, puntos, comas, $, espacios)
        if re.fullmatch(r"[\d\.,\s\$\-]+", p):
            return True
        # Código de glosa: 2 letras mayúsculas + 2-6 dígitos (TA0801, SO0101, etc.)
        if re.fullmatch(r"[A-Z]{2}\d{2,6}", p):
            return True
        return False

    textuales = [p for p in partes if not _es_descartable(p)]
    if not textuales:
        return t
    # El motivo real suele ser el ÚLTIMO segmento textual del listado
    return textuales[-1]


def _concepto_glosa(codigo_glosa: str) -> str:
    """Devuelve la descripción oficial del Manual Único de Glosas (Anexo
    Técnico No. 3) para el código dado. Usa el catálogo completo; si no
    hay match exacto, cae al concepto interno legacy o a fallback."""
    if not codigo_glosa:
        return ""
    # 1) Catálogo oficial completo (nueva fuente de verdad)
    try:
        from app.services.catalogo_glosas import obtener_concepto
        oficial = obtener_concepto(codigo_glosa)
        if oficial:
            return oficial
    except Exception:
        pass
    # 2) Legacy CONCEPTOS_CODIGOS (compatibilidad)
    key = codigo_glosa[:4].upper()
    if key in CONCEPTOS_CODIGOS:
        return CONCEPTOS_CODIGOS[key]
    # 3) Fallback por prefijo de 2 letras
    prefijo = codigo_glosa[:2].upper()
    fallbacks = {
        "TA": "Diferencia tarifaria con los valores pactados o establecidos por la norma",
        "SO": "Falta de soportes o documentación requerida",
        "AU": "Ausencia o diferencia de autorización previa",
        "CO": "Servicio no incluido en cobertura",
        "CL": "Procedimiento no pertinente según criterio clínico",
        "PE": "Procedimiento no pertinente según criterio clínico",
        "FA": "Diferencia en cantidades o error administrativo en facturación",
        "SA": "Glosa por incumplimiento de indicadores del acuerdo de voluntades",
        "IN": "Diferencia o no reconocimiento de insumos",
        "ME": "Diferencia o no reconocimiento de medicamentos",
    }
    return fallbacks.get(prefijo, "Glosa sin concepto específico asignado")


def _facturado_linea_cups(texto: str, cups: str) -> float:
    """Busca el valor de LÍNEA del CUPS específico en la factura.

    En facturas HUS multi-CUPS el "VALOR TOTAL ORDEN DE SERVICIO" es
    la suma de TODOS los ítems — NO sirve cuando la glosa ataca un
    CUPS puntual. Esta función busca el CUPS y toma el último monto
    monetario en su ventana cercana (que en formato HUS suele ser
    "VR ENT" — el valor entregado de esa fila).

    Retorna 0.0 si no encuentra match razonable.
    """
    if not texto or not cups:
        return 0.0
    cups_norm = re.escape(str(cups).strip().upper())
    if not cups_norm:
        return 0.0
    # Ventana de hasta 300 chars después del CUPS, recortada al primer
    # marcador de cierre de fila o bloque (otro código tipo CUPS al
    # inicio de línea, totalizadores). Sin esto en facturas multi-CUPS
    # terminamos atrapando montos de la siguiente fila o el TOTAL
    # ORDEN DE SERVICIO.
    m = re.search(cups_norm + r"(.{0,300})", texto.upper(), re.DOTALL)
    if not m:
        return 0.0
    chunk = m.group(1)
    cortes = [
        r"VALOR\s+SUBTOTAL",
        r"VALOR\s+TOTAL\s+ORDEN",
        r"VALOR\s+CUOTA",
        r"VALOR\s+ANTICIPO",
        r"NOTAS?\s+FINALES",
        r"\bTOTAL\b\s*:\s*",
        # Inicio de fila siguiente: salto de línea + código (mezcla
        # de mayúsculas, dígitos y guiones) seguido de espacio y un
        # caracter de descripción (letra mayúscula o paréntesis).
        # Captura tanto "FMQ0178-3 TRANSAMINASA" como "39147B-18 CONSULTA"
        # como "902210 HEMOGRAMA".
        r"\n\s*[A-Z0-9][A-Z0-9-]{2,12}\s+[A-ZÁÉÍÓÚÑ(]",
    ]
    for pat in cortes:
        cm = re.search(pat, chunk)
        if cm:
            chunk = chunk[: cm.start()]
    # Heurística anti-falso-positivo: una fila de factura legítima
    # tiene >= 2 valores monetarios (CANT + VR UNIT + VR PAC + VR
    # ENT, mínimo 2 con $). Si solo hay 1, casi seguro es texto de
    # glosa donde la única cifra es el OBJETADO — no el facturado.
    todos_montos = re.findall(r"\$\s*[\d][\d.,]{2,}", chunk)
    if len(todos_montos) < 2:
        return 0.0
    # Capturar todos los $<valor> del fragmento (tolera espacios).
    montos = re.findall(r"\$\s*([\d][\d\.,]{2,})", chunk)
    if not montos:
        return 0.0
    # Filtrar ceros ($0,00) y quedarnos con valores significativos.
    def _tof(s):
        s = re.sub(r"[^\d,\.]", "", s)
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        else:
            mm = re.match(r"^(\d+)[\.,](\d{1,2})$", s)
            if mm:
                s = f"{mm.group(1)}.{mm.group(2)}"
            else:
                s = s.replace(".", "").replace(",", "")
        try:
            return float(s)
        except ValueError:
            return 0.0
    valores = [_tof(x) for x in montos]
    valores = [v for v in valores if v > 0]
    if not valores:
        return 0.0
    # En facturas HUS la fila típica es "CANT  VR_UNIT  VR_PAC  VR_ENT".
    # El último monto significativo del chunk suele ser VR_ENT (valor
    # final de la línea). Si los dos últimos coinciden (cantidad=1 →
    # vr_unit == vr_ent), ambos son válidos.
    return valores[-1]


def _extraer_valores_glosa(texto: str, cups: Optional[str] = None) -> dict:
    """Extrae valores de COP mencionados en el texto libre de la glosa.

    La EPS suele escribir "facturada por $114.900 y reconocida solo por
    $90.000, objetándose $24.900". Esta función intenta identificar esos
    tres valores con regex tolerante (acepta $, pesos, puntos, comas).

    Si se pasa `cups`, primero intenta extraer el valor de LÍNEA del
    CUPS en la factura — más preciso que el total cuando la factura
    tiene múltiples ítems. Solo cae al patrón TOTAL/SUBTOTAL si la
    búsqueda CUPS-específica falla.

    Devuelve: {facturado, reconocido, objetado}. Si no se encuentra un
    valor, queda 0.0. Siempre devuelve las tres claves.
    """
    if not texto:
        return {"facturado": 0.0, "reconocido": 0.0, "objetado": 0.0}
    t = texto.upper()

    def _val(raw: str) -> float:
        if not raw:
            return 0.0
        s = re.sub(r"[^\d,\.]", "", raw)
        if not s:
            return 0.0
        # Normalizar formato COP: si hay ambos . y , tratar como miles/decimal
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        else:
            m = re.match(r"^(\d+)[\.,](\d{1,2})$", s)
            if m:
                s = f"{m.group(1)}.{m.group(2)}"
            else:
                s = s.replace(".", "").replace(",", "")
        try:
            return float(s)
        except ValueError:
            return 0.0

    patrones_fact = [
        # Factura electrónica HUS — totalizadores al pie de la FEV.
        # "VALOR TOTAL ORDEN DE SERVICIO   $ 247.663,00"
        # "VALOR SUBTOTAL DE SERVICIOS PRESTADOS  $247.663"
        r"VALOR\s+TOTAL\s+ORDEN\s+DE\s+SERVICIO[:\s]*\$?\s*([\d][\d\.,]{3,})",
        r"VALOR\s+SUBTOTAL\s+DE\s+SERVICIOS\s+PRESTADOS[:\s]*\$?\s*([\d][\d\.,]{3,})",
        # Columna "VR ENT" (valor entregado al cliente) de la fila
        # de concepto en la factura HUS.
        r"VR\s+ENT[:\s]*\$?\s*([\d][\d\.,]{3,})",
        # Forma explícita de HUS: "VALOR UNITARIO FACTURADO POR IPS $ 206,400"
        # o "FACTURADO POR IPS $XXX" (tolera hasta 3 palabras entre POR y el valor)
        r"FACTURAD[OA]S?\s+(?:POR\s+(?:\w+\s+){0,3})?\$?\s*([\d][\d\.,]{3,})",
        r"VALOR\s+(?:UNITARIO\s+)?FACTURADO[:\s]+(?:POR\s+(?:\w+\s+){0,3})?\$?\s*([\d][\d\.,]{3,})",
        r"COBRAD[OA]\s+(?:POR\s+(?:\w+\s+){0,3})?\$?\s*([\d][\d\.,]{3,})",
        r"FACTURA[:\s]+\$?\s*([\d][\d\.,]{3,})",
    ]
    patrones_rec = [
        # Patrón Famisanar/similar: "VALOR UNITARIO CONTRATADO PARA LA FECHA
        # DE PRESTACIÓN DEL SERVICIO CON EPS FAMISANAR 168,000"
        # La palabra "VALOR" o "UNITARIO" antes de CONTRATADO evita falsos
        # positivos con "TARIFA CONTRATADA CON EPS" (mención general).
        r"(?:VALOR|UNITARIO)\s+(?:UNITARIO\s+)?CONTRATAD[OA][^\d$]{0,140}\$?\s*([\d][\d\.,]{3,})",
        r"RECONOCID[OA]S?\s+(?:SOLO\s+)?(?:POR\s+|EN\s+|:\s*)?\$?\s*([\d][\d\.,]{3,})",
        r"ACEPTAD[OA]S?\s+(?:POR\s+|EN\s+)?\$?\s*([\d][\d\.,]{3,})",
        r"VALOR\s+ACEPTADO[:\s]+\$?\s*([\d][\d\.,]{3,})",
        # "PAGA $X", "CUBRE $X"
        r"PAGAD[OA]S?\s+(?:POR\s+)?\$?\s*([\d][\d\.,]{3,})",
    ]
    patrones_obj = [
        r"OBJET[ÁA]NDOSE\s+(?:UNA\s+DIFERENCIA\s+DE\s+)?\$?\s*([\d][\d\.,]{3,})",
        r"OBJETAD[OA]S?\s+(?:POR\s+)?\$?\s*([\d][\d\.,]{3,})",
        r"DIFERENCIA\s+(?:DE\s+)?\$?\s*([\d][\d\.,]{3,})",
        r"GLOSAD[OA]S?\s+(?:POR\s+)?\$?\s*([\d][\d\.,]{3,})",
    ]

    def _primer_match(patrones: list) -> float:
        for pat in patrones:
            m = re.search(pat, t)
            if m:
                v = _val(m.group(1))
                if v > 0:
                    return v
        return 0.0

    # Si tenemos el CUPS, primero intentamos el valor de línea
    # específico — más preciso en facturas multi-CUPS. Si no hay
    # match, caemos a los patrones generales (incluido el TOTAL).
    val_fact = 0.0
    if cups:
        val_fact = _facturado_linea_cups(t, cups)
    if val_fact <= 0:
        val_fact = _primer_match(patrones_fact)

    return {
        "facturado": val_fact,
        "reconocido": _primer_match(patrones_rec),
        "objetado": _primer_match(patrones_obj),
    }


def _generar_banner_tarifa_html(info_tarifa: dict) -> str:
    """Construye un banner HTML con los datos de la tarifa pactada y
    la recomendación de acción para el auditor. Se prepend al dictamen.

    Estilo: caja destacada verde/amarillo/rojo según la recomendación.
    """
    if not info_tarifa or not info_tarifa.get("encontrada"):
        return ""
    t = info_tarifa.get("tarifa") or {}
    rec = info_tarifa.get("recomendacion") or {}
    val_fact = info_tarifa.get("valor_facturado") or 0.0
    val_obj = info_tarifa.get("valor_objetado") or 0.0
    val_pact = info_tarifa.get("valor_pactado_calc") or 0.0

    accion = (rec.get("accion") or "REVISAR").upper()
    color_bg = {
        "DEFENDER_TOTAL": "#ecfdf5",
        "ACEPTAR_PARCIAL": "#fef3c7",
        "REVISAR": "#fee2e2",
    }.get(accion, "#f1f5f9")
    color_border = {
        "DEFENDER_TOTAL": "#10b981",
        "ACEPTAR_PARCIAL": "#d97706",
        "REVISAR": "#dc2626",
    }.get(accion, "#64748b")

    val_rec = info_tarifa.get("valor_reconocido") or 0.0
    tipo = t.get("tipo_tarifa", "VALOR_FIJO")
    factor = float(t.get("factor_ajuste") or 0.0)
    if tipo == "SOAT_PORCENTAJE":
        signo = "+" if factor > 0 else ""
        if val_pact > 0:
            pact_txt = f"SOAT {signo}{factor:.0f}% (pactado ${val_pact:,.0f})"
        else:
            pact_txt = f"SOAT {signo}{factor:.0f}% (SOAT base no cargado)"
    else:
        pact_txt = f"${val_pact:,.0f}"

    import html as _html
    esc = _html.escape

    # Filas dinámicas de la tabla
    filas_tabla = [
        ("Tarifa pactada en contrato", f'<b style="color:#059669;">{pact_txt}</b>'),
    ]
    if val_fact > 0:
        filas_tabla.append(("Valor facturado HUS", f"${val_fact:,.0f}"))
    if val_rec > 0:
        filas_tabla.append(("Valor reconocido EPS", f"${val_rec:,.0f}"))
    if val_obj > 0:
        filas_tabla.append((
            "Valor objetado EPS",
            f'<b style="color:#b91c1c;">${val_obj:,.0f}</b>',
        ))

    tabla_html = (
        '<table style="width:100%;border-collapse:collapse;font-size:.85rem;'
        'background:white;border-radius:6px;overflow:hidden;margin-bottom:.6rem;">'
        '<tr style="background:#f8fafc;">'
        '<th style="padding:6px 10px;text-align:left;border-bottom:1px solid #e2e8f0;">Concepto</th>'
        '<th style="padding:6px 10px;text-align:right;border-bottom:1px solid #e2e8f0;">Valor</th>'
        "</tr>"
    )
    for i, (k, v) in enumerate(filas_tabla):
        bg = "#fafafa" if i % 2 else "white"
        tabla_html += (
            f'<tr style="background:{bg};">'
            f'<td style="padding:6px 10px;">{esc(k)}</td>'
            f'<td style="padding:6px 10px;text-align:right;">{v}</td>'
            "</tr>"
        )
    tabla_html += "</table>"

    # Interpretación SOAT base (si aplica)
    interp_html = ""
    if tipo == "SOAT_PORCENTAJE":
        soat_hus = rec.get("soat_base_hus") or 0.0
        soat_eps = rec.get("soat_base_eps") or 0.0
        if soat_hus > 0 or soat_eps > 0:
            interp_html = (
                '<div style="padding:10px 12px;background:#eff6ff;border-radius:6px;'
                'font-size:.82rem;color:#1e3a8a;margin-bottom:.5rem;'
                'border-left:3px solid #3b82f6;">'
                "<b>🔍 Interpretación SOAT base del CUPS (calculada):</b><br>"
                f"• <b>HUS</b>: asumiendo ${val_fact:,.0f} × {1+factor/100:.3f} "
                f"→ SOAT base = <b>${soat_hus:,.0f}</b><br>"
                f"• <b>EPS</b>: asumiendo ${val_rec:,.0f} × {1+factor/100:.3f} "
                f"→ SOAT base = <b>${soat_eps:,.0f}</b><br>"
                "→ Verificar el valor SOAT oficial del CUPS en el <i>Manual "
                "Tarifario SOAT 2026 — Circular Externa 047 de 2025 MinSalud "
                "(UVB 2026 = $12.110)</i>. Fórmula: valor_pesos = Tarifa_UVB × "
                "$12.110, ajustado a centena más próxima."
                "</div>"
            )

    return f"""
<div style="margin:0 0 1rem 0;padding:14px 18px;background:{color_bg};
            border-left:5px solid {color_border};border-radius:8px;
            font-family:system-ui,sans-serif;line-height:1.5;">
  <div style="font-size:1rem;font-weight:700;margin-bottom:.5rem;color:#1e293b;">
    📋 Tarifa pactada encontrada en el contrato · {esc(rec.get('titulo', ''))}
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
              gap:.4rem .9rem;font-size:.85rem;margin-bottom:.5rem;">
    <div><b>CUPS:</b> {esc(str(t.get('codigo_cups') or '—'))}</div>
    <div><b>EPS:</b> {esc(str(t.get('eps') or '—'))}</div>
    <div><b>Contrato:</b> {esc(str(t.get('contrato_numero') or '—'))}</div>
    <div><b>Modalidad:</b> {esc(str(t.get('modalidad') or '—'))}</div>
  </div>
  <div style="font-size:.82rem;color:#334155;margin-bottom:.6rem;">
    <b>Descripción contrato:</b> {esc(str(t.get('descripcion') or '—'))}
  </div>
  {tabla_html}
  {interp_html}
  <div style="padding:10px 12px;background:white;border-radius:6px;
              font-size:.85rem;color:#0f172a;">
    <b>💡 Recomendación:</b> {esc(rec.get('razon', ''))}
  </div>
  <div style="font-size:.72rem;color:#64748b;margin-top:.5rem;">
    Fuente: {esc(str(t.get('fuente_archivo') or 'contrato'))}
    {("· Vigencia hasta: " + esc(t['vigencia_hasta'][:10])) if t.get('vigencia_hasta') else ""}
  </div>
</div>
"""


def _extraer_cups_servicio(texto_glosa: str, contexto_pdf: str = "") -> tuple[str, str]:
    """Extrae tupla (CUPS, descripción_servicio) desde el texto de la glosa/PDF.

    PRIORIDAD para el CUPS:
      1. En el TEXTO DE LA GLOSA, buscar un número de 4-8 dígitos delimitado
         por guiones/espacios después del código del tipo (FA0202 - ... - 890602 - ...).
      2. Si no, cualquier número 5-6 dígitos EN EL TEXTO DE LA GLOSA.
      3. Nunca como último recurso mirar el PDF (allí hay números de ingreso,
         HC, folio que no son CUPS).

    Retorna ("", "") si no logra identificarlos.
    """
    if not texto_glosa and not contexto_pdf:
        return "", ""

    cups = ""
    # Códigos de glosa (NO son CUPS) — TA0801, SO0101, FA0202, CO0301, etc.
    # Si el regex captura uno de estos, lo descartamos y seguimos buscando.
    GLOSA_CODES = re.compile(r"^(TA|SO|FA|CO|CL|PE|AU|IN|ME|SE|EX)\d{2,4}$")

    def _es_cups_valido(token: str) -> bool:
        if not token or GLOSA_CODES.match(token):
            return False
        # Debe tener al menos 4 dígitos (CUPS reales son 4-8 dígitos)
        digitos = sum(1 for c in token if c.isdigit())
        return digitos >= 4

    # 1) Patrón específico del formato de glosa: "- 890602 -" o "- 890602 ESTUDIO…"
    # Acepta también sufijos alfanuméricos del HUS: "372301H", "039001H1",
    # "39147B-18", "FMQ6296", "19914262-04" (medicamentos CUM), etc.
    if texto_glosa:
        # Itera todos los matches; toma el primero que NO sea código de glosa
        for m in re.finditer(
            r"(?:^|\s|[-·,])\s*([A-Z]{0,3}\d{4,8}[A-Z]?\d{0,2}(?:-\d{1,3})?)\s*(?:[-·,]|\s+[A-ZÁÉÍÓÚÑ])",
            texto_glosa,
        ):
            cand = m.group(1)
            if _es_cups_valido(cand):
                cups = cand
                break

    # 2) Si no, cualquier número de 5-6 dígitos (con sufijo opcional) en el
    # texto de la glosa. Acepta "890202", "372301H", "39147B-18".
    if not cups and texto_glosa:
        for m in re.finditer(r"\b(\d{5,6}[A-Z]?\d{0,2}(?:-\d{1,3})?)\b", texto_glosa):
            cand = m.group(1)
            if _es_cups_valido(cand):
                cups = cand
                break
        if not cups:
            # Medicamentos tipo "19914262-04" o "FMQ6296"
            for m in re.finditer(r"\b([A-Z]{3}\d{4,8}|\d{7,10}-\d{1,3})\b", texto_glosa):
                cand = m.group(1)
                if _es_cups_valido(cand):
                    cups = cand
                    break

    # Nota: NO usamos el PDF para extraer CUPS porque contiene otros números
    # (ingreso, historia clínica, folio) que no son CUPS. Si el texto de la
    # glosa no lo tiene, mejor devolver vacío.

    fuente = f"{texto_glosa}\n{contexto_pdf}"
    servicio = ""
    # Buscar descripción del servicio con patrones comunes
    for pat in [
        r"(?:SERVICIO|PROCEDIMIENTO|DESCRIPCI[ÓO]N)\s*[:\-]\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,\-/]{5,120})",
        r"\b(CONSULTA\s+[A-ZÁÉÍÓÚÑ ,\-]{3,100})",
        r"\b(CIRUG[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,100})",
        r"\b(ESTUDIO\s+[A-ZÁÉÍÓÚÑ ,\-]{3,100})",
        r"\b(TOMOGRAF[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,80})",
        r"\b(RESONANCIA\s+[A-ZÁÉÍÓÚÑ ,\-]{3,80})",
        r"\b(ECOGRAF[ÍI]A\s+[A-ZÁÉÍÓÚÑ ,\-]{3,80})",
        r"\b(BIOPSIA[A-ZÁÉÍÓÚÑ ,\-]{0,80})",
        r"\b(ACETAMINOFEN[A-ZÁÉÍÓÚÑ0-9 ,\-/]{0,80})",
    ]:
        m = re.search(pat, fuente, re.IGNORECASE)
        if m:
            servicio = (m.group(1) if m.groups() else m.group(0)).strip()
            servicio = re.split(r"\s+(?:COBRO|DIFERENCIA|MAYOR|VALOR|MOTIVO)", servicio)[0]
            servicio = re.sub(r"\s+", " ", servicio).strip().rstrip(",-.")[:200]
            break

    return cups, servicio


def _descripcion_servicio(codigo_glosa: str, texto_glosa: str = "", contexto_pdf: str = "") -> str:
    """Devuelve una descripción del servicio detectado en la glosa/soportes.
    Si no logra detectar un servicio específico, devuelve una frase neutra según el
    prefijo del código (TA, SO, AU...)."""
    detectado = _detectar_servicio_desde_texto(texto_glosa, contexto_pdf)
    if detectado:
        return f"AL SERVICIO FACTURADO {detectado}"

    # Fallback neutro según el tipo de glosa (sin ejemplos entre paréntesis)
    if not codigo_glosa:
        return "AL SERVICIO FACTURADO"
    prefijo = codigo_glosa[:2].upper()
    return {
        "TA": "AL SERVICIO FACTURADO",
        "SO": "AL SERVICIO FACTURADO Y SUS SOPORTES DOCUMENTALES",
        "AU": "AL PROCEDIMIENTO AUTORIZADO",
        "CO": "AL SERVICIO CUBIERTO",
        "CL": "AL PROCEDIMIENTO MÉDICO PRESTADO",
        "PE": "AL PROCEDIMIENTO MÉDICO PRESTADO",
        "FA": "AL CARGO FACTURADO",
        "IN": "AL INSUMO O DISPOSITIVO MÉDICO UTILIZADO",
        "ME": "AL MEDICAMENTO DISPENSADO",
    }.get(prefijo, "AL SERVICIO FACTURADO")
