"""Extractor automático de datos de facturas médicas desde PDF.

Ronda 5 de la visión premium. Cuando el gestor sube un PDF de una factura
glosada, este servicio extrae SIN IA (usando pdfplumber + regex) los campos
clave: número de factura, paciente, fecha, valor, CUPS, EPS, glosa (TA/SO/
FA...), valor objetado, etc.

Si hay ambigüedades, la IA (Claude Vision) puede usarse como fallback
vía PdfService.extraer_con_ocr ya existente — pero esta capa prioriza
extracción determinística (gratis, rápida, reproducible).

Output:
  {
    "numero_factura": str,
    "numero_radicado": str,
    "eps": str,
    "paciente": str,
    "fecha_radicacion": date str,
    "fecha_recepcion": date str,
    "cups": str,
    "servicio": str,
    "valor_facturado": float,
    "valor_reconocido": float,
    "valor_objetado": float,
    "codigos_glosa": list[str],
    "confianza": 0.0-1.0,   # qué tan seguro está el extractor
    "campos_faltantes": list[str],
  }
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional


# ─── Helpers genéricos ──────────────────────────────────────────────────────

_CODIGOS_GLOSA = re.compile(r"\b(TA|SO|FA|CO|CL|PE|AU|IN|ME|SE|EX)\d{2,4}\b")
_FACTURA_RE = re.compile(
    r"(?:(?:FACTURA|FACT|FV|FE|HUS)[\s:.\-#]*)"   # prefijo variado
    r"([A-Z0-9\-]{4,30})",                           # el número
    re.IGNORECASE,
)
_RADICADO_RE = re.compile(
    r"(?:RADICAD[OA]|RAD\.?|N[º°]?\s*RADICADO)[\s:.\-#]*([A-Z0-9\-]{4,30})",
    re.IGNORECASE,
)
_CUPS_RE = re.compile(
    r"\b(?:CUPS|C\.U\.P\.S\.?)[\s:.\-]*([A-Z]{0,3}\d{4,8}[A-Z]?\d{0,2}(?:-\d{1,3})?)\b",
    re.IGNORECASE,
)
_VALOR_RE = re.compile(
    r"\$\s*([\d][\d\.,]{2,})(?:\s|$)",
)


def _parsear_valor_cop(raw: str) -> float:
    if not raw:
        return 0.0
    s = re.sub(r"[^\d,\.]", "", raw)
    if not s:
        return 0.0
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


def _parsear_fecha(raw: str) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


_EPS_CONOCIDAS = [
    "FAMISANAR", "NUEVA EPS", "COOSALUD", "COMPENSAR", "POSITIVA", "FOMAG",
    "SANITAS", "SALUD TOTAL", "SURA", "ECOOPSOS", "POLICIA NACIONAL",
    "DISPENSARIO MEDICO", "SUMIMEDICAL", "PRECIMED", "AURORA",
    "SALUD MIA", "PPL", "COMFENALCO", "CAJACOPI",
]


# ─── Extractor principal ────────────────────────────────────────────────────

def extraer_de_texto(texto: str) -> dict:
    """Extrae los campos clave de un texto extraído del PDF.

    Usa regex + heurísticas. Devuelve dict con los campos identificados
    + score de confianza basado en cuántos campos pudo encontrar.
    """
    if not texto or len(texto) < 30:
        return _resultado_vacio("Texto demasiado corto")
    t = texto.replace("\n", " ").replace("\r", " ")
    t_upper = t.upper()

    resultado = {
        "numero_factura": "",
        "numero_radicado": "",
        "eps": "",
        "paciente": "",
        "fecha_radicacion": "",
        "fecha_recepcion": "",
        "cups": "",
        "servicio": "",
        "valor_facturado": 0.0,
        "valor_reconocido": 0.0,
        "valor_objetado": 0.0,
        "codigos_glosa": [],
        "confianza": 0.0,
        "campos_faltantes": [],
    }

    # Número de factura
    m = _FACTURA_RE.search(t_upper)
    if m:
        cand = m.group(1).strip()
        # Evitar capturas espurias como "No." "DE" "CON"
        if len(cand) >= 4 and not cand.isalpha():
            resultado["numero_factura"] = cand

    # Número de radicado
    m = _RADICADO_RE.search(t_upper)
    if m:
        resultado["numero_radicado"] = m.group(1).strip()

    # EPS — buscar nombres conocidos
    for eps in _EPS_CONOCIDAS:
        if eps in t_upper:
            resultado["eps"] = eps
            break

    # CUPS
    m = _CUPS_RE.search(t_upper)
    if m:
        resultado["cups"] = m.group(1)

    # Códigos de glosa — findall devuelve solo el grupo (prefijo),
    # por eso usamos finditer para obtener el código completo.
    codigos_completos = [mm.group(0) for mm in _CODIGOS_GLOSA.finditer(t_upper)]
    resultado["codigos_glosa"] = sorted(set(codigos_completos))

    # Fechas tipo "RADICACIÓN: 15/04/2026" o "RECEPCIÓN: 20/04/2026"
    m_rad = re.search(
        r"RADICACI[ÓO]N[\s:.\-]+(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})",
        t_upper,
    )
    if m_rad:
        f = _parsear_fecha(m_rad.group(1))
        if f:
            resultado["fecha_radicacion"] = f

    m_rec = re.search(
        r"RECEPCI[ÓO]N[\s:.\-]+(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})",
        t_upper,
    )
    if m_rec:
        f = _parsear_fecha(m_rec.group(1))
        if f:
            resultado["fecha_recepcion"] = f

    # Valores: usar regex específicos primero
    # "FACTURADO: $X" o "VALOR FACTURADO: $X"
    for pat in [
        r"FACTURAD[OA]\s*(?:POR\s+(?:\w+\s+){0,3})?\$?\s*([\d][\d\.,]{3,})",
        r"VALOR\s+(?:UNITARIO\s+)?FACTURADO\s*[:\s]+\$?\s*([\d][\d\.,]{3,})",
    ]:
        m = re.search(pat, t_upper)
        if m:
            v = _parsear_valor_cop(m.group(1))
            if v > 0:
                resultado["valor_facturado"] = v
                break

    for pat in [
        r"RECONOCID[OA]\s*(?:SOLO\s+)?(?:POR\s+)?\$?\s*([\d][\d\.,]{3,})",
        r"VALOR\s+RECONOCIDO\s*[:\s]+\$?\s*([\d][\d\.,]{3,})",
        r"VALOR\s+(?:UNITARIO\s+)?CONTRATAD[OA][^\d$]{0,140}\$?\s*([\d][\d\.,]{3,})",
    ]:
        m = re.search(pat, t_upper)
        if m:
            v = _parsear_valor_cop(m.group(1))
            if v > 0:
                resultado["valor_reconocido"] = v
                break

    for pat in [
        r"OBJET[ÁA]NDOSE\s+(?:UNA\s+DIFERENCIA\s+DE\s+)?\$?\s*([\d][\d\.,]{3,})",
        r"OBJETAD[OA]\s*(?:POR\s+)?\$?\s*([\d][\d\.,]{3,})",
        r"DIFERENCIA\s+(?:DE\s+)?\$?\s*([\d][\d\.,]{3,})",
        r"GLOSAD[OA]\s*(?:POR\s+)?\$?\s*([\d][\d\.,]{3,})",
    ]:
        m = re.search(pat, t_upper)
        if m:
            v = _parsear_valor_cop(m.group(1))
            if v > 0:
                resultado["valor_objetado"] = v
                break

    # Paciente: heurística "PACIENTE: NOMBRE APELLIDO"
    m = re.search(
        r"PACIENTE[\s:]+([A-ZÁÉÍÓÚÑ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ]{2,}){1,4})",
        t_upper,
    )
    if m:
        resultado["paciente"] = m.group(1).title().strip()

    # Servicio: heurística "SERVICIO:" o la descripción después del CUPS
    m = re.search(
        r"(?:SERVICIO|PROCEDIMIENTO|DESCRIPCI[ÓO]N)\s*[:\-]\s*"
        r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,\-/]{10,120})",
        t_upper,
    )
    if m:
        servicio = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",-.")[:200]
        resultado["servicio"] = servicio

    # ─── Score de confianza ─────────────────────────────────────────────────
    campos_obligatorios = ["numero_factura", "eps", "cups", "codigos_glosa", "valor_objetado"]
    presentes = sum(
        1 for k in campos_obligatorios
        if resultado.get(k) not in ("", 0, 0.0, [], None)
    )
    resultado["confianza"] = round(presentes / len(campos_obligatorios), 2)
    resultado["campos_faltantes"] = [
        k for k in campos_obligatorios
        if resultado.get(k) in ("", 0, 0.0, [], None)
    ]

    return resultado


def _resultado_vacio(razon: str) -> dict:
    return {
        "numero_factura": "",
        "numero_radicado": "",
        "eps": "",
        "paciente": "",
        "fecha_radicacion": "",
        "fecha_recepcion": "",
        "cups": "",
        "servicio": "",
        "valor_facturado": 0.0,
        "valor_reconocido": 0.0,
        "valor_objetado": 0.0,
        "codigos_glosa": [],
        "confianza": 0.0,
        "campos_faltantes": ["(texto vacío o inválido)"],
        "error": razon,
    }
