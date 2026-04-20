"""
validador_dictamen.py — Checklist pre-radicación de 10 puntos
==============================================================
Evalúa un dictamen antes de radicarlo ante la EPS. Cada check tiene peso
diferente según criticidad. Score total 0-100.

Umbrales:
  • 90-100: APROBADO — listo para radicar
  • 70-89:  ACEPTABLE — radicar con observaciones menores
  • 50-69:  REQUIERE REFINAR — corregir antes de radicar
  • 0-49:   RECHAZADO — reescribir
"""
from __future__ import annotations
import re
from html import unescape
from typing import Optional


def _limpiar_html(html: str) -> str:
    """Extrae texto plano del HTML del dictamen."""
    if not html:
        return ""
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", unescape(txt)).strip()
    return txt


def _contar_palabras(texto: str) -> int:
    """Cuenta palabras (separadas por espacios)."""
    if not texto:
        return 0
    return len(texto.split())


# Cada check retorna {nombre, peso, aprobado, mensaje, sugerencia}
def check_apertura(texto: str) -> dict:
    nombre = "Apertura institucional correcta"
    peso = 10
    tiene = "ESE HUS NO ACEPTA" in texto.upper()
    sin_respetuosamente = not re.search(
        r"\bESE\s+HUS\s+RESPETUOSAMENTE\s+NO\s+ACEPTA\b", texto, re.IGNORECASE
    )
    aprobado = tiene and sin_respetuosamente
    if not tiene:
        msg = "Apertura debe iniciar con 'ESE HUS NO ACEPTA...'"
    elif not sin_respetuosamente:
        msg = "No usar 'RESPETUOSAMENTE' en la apertura (va solo en el cierre)"
    else:
        msg = "Apertura correcta"
    return {
        "id": "apertura", "nombre": nombre, "peso": peso,
        "aprobado": aprobado, "mensaje": msg,
        "sugerencia": "" if aprobado else "Verifica el inicio del argumento",
    }


def check_cups_real(texto: str, cups_esperado: Optional[str]) -> dict:
    nombre = "CUPS del expediente citado correctamente"
    peso = 10
    t = texto.upper()
    if cups_esperado and cups_esperado != "N/A":
        aprobado = cups_esperado in t
        msg = (
            f"CUPS {cups_esperado} citado correctamente"
            if aprobado else f"No se encontró el CUPS {cups_esperado} en el texto"
        )
    else:
        # No hay CUPS específico; verificar que no haya CUPS inventado
        inventados = re.findall(r"\bCUPS\s+\d{6}\b", t)
        aprobado = len(inventados) == 0 or "CUPS INDICADO EN EL EXPEDIENTE" in t
        msg = (
            "No se detectaron CUPS inventados" if aprobado
            else f"Posible CUPS inventado: {', '.join(set(inventados[:3]))}"
        )
    return {
        "id": "cups", "nombre": nombre, "peso": peso,
        "aprobado": aprobado, "mensaje": msg,
        "sugerencia": "" if aprobado else "Cita SOLO el CUPS que aparece en el texto de la glosa",
    }


def check_sin_cifras_inventadas(texto: str, valor_original: Optional[str]) -> dict:
    nombre = "Sin cifras monetarias inventadas"
    peso = 15
    # Extraer todas las cifras tipo $NNN.NNN
    cifras = re.findall(r"\$\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?", texto)
    valor_real_limpio = (valor_original or "").replace(" ", "").replace(".", "").replace(",", "")
    if not cifras:
        aprobado = True
        msg = "Sin cifras monetarias"
    elif valor_real_limpio and valor_real_limpio not in ("$0", "$000"):
        # Hay valor real en la glosa — permitido usar cifras
        aprobado = True
        msg = f"{len(cifras)} cifra(s) citada(s) (glosa tiene valor original)"
    else:
        # No hay valor real pero se citan cifras
        aprobado = False
        msg = f"Posibles cifras inventadas: {', '.join(cifras[:3])}"
    return {
        "id": "cifras", "nombre": nombre, "peso": peso,
        "aprobado": aprobado, "mensaje": msg,
        "sugerencia": "" if aprobado else 'Usa "EL VALOR INDICADO EN EL EXPEDIENTE"',
    }


def check_normas_citadas(texto: str, codigo_glosa: str) -> dict:
    nombre = "Al menos 3 normas del catálogo vigente"
    peso = 15
    t = texto.upper()
    # Conteo de referencias normativas
    patrones = [
        r"LEY\s+\d+\s+DE\s+\d{4}",
        r"DECRETO\s+\d+\s+DE\s+\d{4}",
        r"RESOLUCI[ÓO]N\s+\d+\s+DE\s+\d{4}",
        r"ART[ÍI]?CULO\s+\d+",
        r"ART\.\s*\d+",
        r"CIRCULAR\s+\d+",
        r"SENTENCIA\s+T[-\s]?\d+",
        r"C[ÓO]DIGO\s+DE\s+COMERCIO",
        r"C[ÓO]DIGO\s+CIVIL",
    ]
    total = sum(len(re.findall(p, t)) for p in patrones)
    aprobado = total >= 3
    msg = f"{total} referencia(s) normativa(s) detectada(s)"
    return {
        "id": "normas", "nombre": nombre, "peso": peso,
        "aprobado": aprobado, "mensaje": msg,
        "sugerencia": "" if aprobado else "Cita al menos 3 normas: artículos, leyes o sentencias",
    }


def check_enumeracion(texto: str) -> dict:
    nombre = "Refutación enumerada (EN PRIMER/SEGUNDO/TERCER LUGAR)"
    peso = 10
    t = texto.upper()
    tiene = (
        "EN PRIMER LUGAR" in t
        and "EN SEGUNDO LUGAR" in t
    )
    msg = "Enumeración presente" if tiene else "Falta enumeración técnica en P2"
    return {
        "id": "enumeracion", "nombre": nombre, "peso": peso,
        "aprobado": tiene, "mensaje": msg,
        "sugerencia": "" if tiene else "Usa 'EN PRIMER LUGAR... EN SEGUNDO LUGAR...'",
    }


def check_reserva_supersalud(texto: str) -> dict:
    nombre = "Reserva de derechos ante SuperSalud"
    peso = 10
    t = texto.upper()
    tiene = (
        "SUPERSALUD" in t
        or "SUPERINTENDENCIA NACIONAL DE SALUD" in t
        or "ART. 126" in t
        or "ART\u00cdCULO 126" in t
        or "ARTÍCULO 126" in t
    )
    msg = "Reserva SuperSalud presente" if tiene else "Falta reserva de derechos ante SuperSalud"
    return {
        "id": "supersalud", "nombre": nombre, "peso": peso,
        "aprobado": tiene, "mensaje": msg,
        "sugerencia": "" if tiene else "Incluye cláusula de reserva Art. 126 Ley 1438/2011",
    }


def check_extension(texto: str) -> dict:
    nombre = "Extensión 230-310 palabras"
    peso = 8
    palabras = _contar_palabras(texto)
    aprobado = 230 <= palabras <= 320 or (palabras < 230 and palabras >= 180)  # margen
    if palabras < 180:
        msg = f"Demasiado corto ({palabras} palabras)"
    elif palabras > 320:
        msg = f"Demasiado largo ({palabras} palabras)"
    else:
        msg = f"{palabras} palabras — dentro del rango"
    return {
        "id": "extension", "nombre": nombre, "peso": peso,
        "aprobado": aprobado, "mensaje": msg,
        "sugerencia": "" if aprobado else "Ajustar a 230-310 palabras",
    }


def check_codigo_respuesta_coherente(texto: str, codigo_respuesta: Optional[str]) -> dict:
    nombre = "Código RE coherente con tono del argumento"
    peso = 8
    t = texto.upper()
    if not codigo_respuesta:
        return {
            "id": "codigo_re", "nombre": nombre, "peso": peso,
            "aprobado": True, "mensaje": "Sin código RE asignado",
            "sugerencia": "",
        }
    reglas = {
        "RE9502": ("EXTEMPOR", "Debe mencionar 'EXTEMPORÁNEA' o plazo vencido"),
        "RE9602": ("INJUSTIFIC", "Debe mencionar 'INJUSTIFICADA'"),
        "RE9901": (None, "OK"),
    }
    patron, sugerencia = reglas.get(codigo_respuesta.upper(), (None, ""))
    if patron is None:
        aprobado = True
        msg = "Coherencia no verificable"
    else:
        aprobado = patron in t
        msg = "Coherente" if aprobado else sugerencia
    return {
        "id": "codigo_re", "nombre": nombre, "peso": peso,
        "aprobado": aprobado, "mensaje": msg,
        "sugerencia": "" if aprobado else sugerencia,
    }


def check_contrato_mencionado(texto: str, eps: str) -> dict:
    nombre = "Menciona contrato o tarifa pactada si aplica"
    peso = 7
    t = texto.upper()
    # Solo aplica si la EPS tiene contrato conocido
    try:
        from app.services.glosa_ia_prompts import get_contrato
        contrato = get_contrato(eps)
        numero = contrato.get("numero", "")
    except Exception:
        numero = ""
    if numero and numero != "SIN CONTRATO PACTADO":
        # Extraer primer token distintivo del número de contrato
        token = numero.split()[0] if numero else ""
        aprobado = token.upper() in t or "CONTRATO" in t
        msg = "Contrato mencionado" if aprobado else f"Omite contrato {numero[:40]}"
    else:
        aprobado = True
        msg = "Sin contrato aplicable (SOAT pleno)"
    return {
        "id": "contrato", "nombre": nombre, "peso": peso,
        "aprobado": aprobado, "mensaje": msg,
        "sugerencia": "" if aprobado else "Menciona el número de contrato en el P3",
    }


def check_placeholders(texto: str) -> dict:
    nombre = "Sin placeholders ni corchetes"
    peso = 7
    # Detectar [ALGO] que no sea parte de cita legal común
    placeholders = re.findall(r"\[[A-Z_]{3,}\]", texto)
    dollar_ph = re.findall(r"\$\s*\[[A-Z_]+\]", texto)
    todos = placeholders + dollar_ph
    aprobado = len(todos) == 0
    msg = (
        "Sin placeholders" if aprobado
        else f"Placeholders detectados: {', '.join(set(todos[:3]))}"
    )
    return {
        "id": "placeholders", "nombre": nombre, "peso": peso,
        "aprobado": aprobado, "mensaje": msg,
        "sugerencia": "" if aprobado else "Elimina [CORCHETES] y $[PLACEHOLDERS]",
    }


def evaluar_dictamen(
    argumento_html: str,
    codigo_glosa: str = "",
    cups_esperado: Optional[str] = None,
    valor_original: Optional[str] = None,
    codigo_respuesta: Optional[str] = None,
    eps: str = "",
) -> dict:
    """Corre los 10 checks sobre un dictamen y retorna score + detalles."""
    texto = _limpiar_html(argumento_html)

    checks = [
        check_apertura(texto),
        check_cups_real(texto, cups_esperado),
        check_sin_cifras_inventadas(texto, valor_original),
        check_normas_citadas(texto, codigo_glosa),
        check_enumeracion(texto),
        check_reserva_supersalud(texto),
        check_extension(texto),
        check_codigo_respuesta_coherente(texto, codigo_respuesta),
        check_contrato_mencionado(texto, eps),
        check_placeholders(texto),
    ]

    peso_total = sum(c["peso"] for c in checks)
    peso_aprobado = sum(c["peso"] for c in checks if c["aprobado"])
    score = round(peso_aprobado / peso_total * 100, 1) if peso_total else 0

    if score >= 90:
        veredicto = "APROBADO"
        color = "#10b981"
    elif score >= 70:
        veredicto = "ACEPTABLE"
        color = "#3b82f6"
    elif score >= 50:
        veredicto = "REQUIERE REFINAR"
        color = "#f59e0b"
    else:
        veredicto = "RECHAZADO"
        color = "#dc2626"

    return {
        "score": score,
        "veredicto": veredicto,
        "color": color,
        "checks": checks,
        "aprobados": sum(1 for c in checks if c["aprobado"]),
        "total": len(checks),
        "palabras": _contar_palabras(texto),
    }
