"""
extractor_folios.py — Detecta folios, páginas y referencias documentales
=========================================================================
Analiza el texto extraído de los PDFs adjuntos para identificar:
  • Números de folio ("folio 59", "fl. 15", "hoja 23")
  • Números de página ("pág. 7", "página 3")
  • Fechas específicas (dd/mm/yyyy)
  • Firmas ("firmado por Dr. X")

Estos datos se inyectan al prompt IA para que la respuesta cite
referencias documentales específicas del expediente, haciendo la
respuesta casi imposible de ratificar por la EPS.
"""
from __future__ import annotations
import re
from collections import Counter


_PATRON_FOLIO = re.compile(
    r"(?:folio|fl\.?|hoja|página|pagina|pág\.?|pag\.?)\s*(?:no?\.?|número|num\.?)?\s*(\d{1,4})",
    re.IGNORECASE,
)
_PATRON_FECHA = re.compile(
    r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b"
)
_PATRON_CIE10 = re.compile(r"\b([A-Z]\d{2}(?:\.\d)?)\b")
_PATRON_CUPS_6D = re.compile(r"\b(\d{6})\b")
_PATRON_HC = re.compile(r"(?:hist\.?\s*cl[íi]nica|historia\s*cl[íi]nica|HC)[\s#:]*(\d{4,12})", re.IGNORECASE)
_PATRON_FIRMA = re.compile(
    r"(?:firmado|firma|suscrito|expedido)\s+por[\s:]*(Dr\.?\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})",
    re.IGNORECASE,
)


def extraer_referencias_documentales(contexto_pdf: str) -> dict:
    """Escanea el contexto PDF y retorna referencias documentales estructuradas.

    Returns:
        {
            "folios_citables": [list of int],     # folios mencionados
            "fechas_citables": [list of str],     # fechas DD/MM/YYYY
            "cie10_encontrados": [list of str],   # códigos CIE-10
            "cups_encontrados": [list of str],    # CUPS de 6 dígitos
            "historias_clinicas": [list of str],
            "firmas_medicos": [list of str],
            "resumen_citable": str,               # texto listo para prompt IA
        }
    """
    if not contexto_pdf:
        return {
            "folios_citables": [],
            "fechas_citables": [],
            "cie10_encontrados": [],
            "cups_encontrados": [],
            "historias_clinicas": [],
            "firmas_medicos": [],
            "resumen_citable": "",
        }

    # Folios (top 5 más frecuentes)
    folios = [int(m) for m in _PATRON_FOLIO.findall(contexto_pdf) if 1 <= int(m) <= 9999]
    folios_top = [f for f, _ in Counter(folios).most_common(5)]

    # Fechas (únicas)
    fechas_raw = _PATRON_FECHA.findall(contexto_pdf)
    fechas_norm = []
    for d, m, y in fechas_raw:
        try:
            dia, mes, ano = int(d), int(m), int(y)
            if len(y) == 2:
                ano = 2000 + ano if ano < 50 else 1900 + ano
            if 1 <= dia <= 31 and 1 <= mes <= 12 and 2020 <= ano <= 2030:
                fechas_norm.append(f"{dia:02d}/{mes:02d}/{ano}")
        except ValueError:
            continue
    fechas_unicas = list(dict.fromkeys(fechas_norm))[:8]

    # CIE-10
    cie10 = list(dict.fromkeys(_PATRON_CIE10.findall(contexto_pdf)))[:6]

    # CUPS
    cups = list(dict.fromkeys(_PATRON_CUPS_6D.findall(contexto_pdf)))[:10]

    # Historias clínicas
    hc = list(dict.fromkeys(_PATRON_HC.findall(contexto_pdf)))[:3]

    # Firmas
    firmas = list(dict.fromkeys(_PATRON_FIRMA.findall(contexto_pdf)))[:3]

    # Resumen citable para el prompt
    lineas = []
    if folios_top:
        lineas.append(f"  • Folios del expediente referenciables: {', '.join(str(f) for f in folios_top)}")
    if fechas_unicas:
        lineas.append(f"  • Fechas documentales: {', '.join(fechas_unicas[:5])}")
    if hc:
        lineas.append(f"  • Historia(s) clínica(s) N°: {', '.join(hc)}")
    if firmas:
        lineas.append(f"  • Firma(s) identificada(s): {'; '.join(firmas)}")
    if cie10:
        lineas.append(f"  • Diagnóstico(s) CIE-10: {', '.join(cie10)}")
    if cups:
        lineas.append(f"  • CUPS presentes en soporte: {', '.join(cups[:5])}")

    resumen = "\n".join(lineas) if lineas else "  (sin referencias documentales específicas detectadas)"

    return {
        "folios_citables": folios_top,
        "fechas_citables": fechas_unicas,
        "cie10_encontrados": cie10,
        "cups_encontrados": cups,
        "historias_clinicas": hc,
        "firmas_medicos": firmas,
        "resumen_citable": resumen,
    }
