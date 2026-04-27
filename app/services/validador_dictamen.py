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


def check_invitacion_conciliacion(texto: str) -> dict:
    nombre = "Invitación a conciliación de auditoría"
    peso = 10
    t = texto.upper()
    tiene = (
        "CONCILIACI" in t
        or "ART. 20 DEC. 4747" in t
        or "ART\u00cdCULO 20 DEL DECRETO 4747" in t
        or "ARTÍCULO 20 DEL DECRETO 4747" in t
    )
    msg = "Invitación a conciliación presente" if tiene else "Falta invitación a mesa de conciliación"
    return {
        "id": "conciliacion", "nombre": nombre, "peso": peso,
        "aprobado": tiene, "mensaje": msg,
        "sugerencia": "" if tiene else "Incluye invitación a mesa de conciliación (Art. 20 Dec. 4747/2007)",
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


def check_cita_literal_normativa(texto: str) -> dict:
    """NUEVO: verifica que haya al menos una cita textual entre comillas.

    Las respuestas con cita literal («...») son más difíciles de ratificar
    porque no dejan margen a interpretación.
    """
    nombre = "Cita literal de normativa entre comillas"
    peso = 8
    tiene_cita_literal = bool(re.search(r"[«\"][^«»\"]{30,}[»\"]", texto))
    aprobado = tiene_cita_literal
    msg = (
        "Al menos 1 cita literal de normativa entre comillas ✓"
        if aprobado else "Ninguna cita textual detectada"
    )
    return {
        "id": "cita_literal", "nombre": nombre, "peso": peso,
        "aprobado": aprobado, "mensaje": msg,
        "sugerencia": "" if aprobado else "Cita 1 fragmento textual entre « » de la norma clave",
    }


def check_anti_rebatimiento(texto: str) -> dict:
    """NUEVO: verifica presencia de cláusula anti-rebatimiento."""
    nombre = "Cláusula anti-rebatimiento preventiva"
    peso = 7
    t = texto.upper()
    patrones = [
        "SIN QUE SEA ADMISIBLE",
        "NO SIENDO PROCEDENTE",
        "NO PUEDE TRASLADARSE",
        "CARECE DE RESPALDO CONTRACTUAL",
        "NO RESULTA PROCEDENTE",
        "SIN PERJUICIO DE LO ANTERIOR",
    ]
    aprobado = any(p in t for p in patrones)
    msg = (
        "Cláusula anti-rebatimiento presente ✓"
        if aprobado else "Sin cláusula preventiva"
    )
    return {
        "id": "anti_rebatimiento", "nombre": nombre, "peso": peso,
        "aprobado": aprobado, "mensaje": msg,
        "sugerencia": "" if aprobado else "Añade una cláusula anti-rebatimiento preventiva",
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
        check_invitacion_conciliacion(texto),
        check_extension(texto),
        check_codigo_respuesta_coherente(texto, codigo_respuesta),
        check_contrato_mencionado(texto, eps),
        check_placeholders(texto),
        # v2: checks adicionales de blindaje
        check_cita_literal_normativa(texto),
        check_anti_rebatimiento(texto),
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


# ═══════════════════════════════════════════════════════════════════════
#  Validación para RETRY automático del cerebro IA (R-cerebro mejora #1)
# ═══════════════════════════════════════════════════════════════════════
#  Diferente al `evaluar_dictamen()` (informativo, score 0-100): aquí
#  detectamos defectos CRÍTICOS que justifican re-llamar al modelo con
#  una instrucción de corrección. Evita que dictámenes con tags faltantes,
#  frases prohibidas o cifras inventadas lleguen al gestor.

# Frases prohibidas según el system prompt (registro hostil/coloquial)
_FRASES_PROHIBIDAS_CRITICAS = [
    "SE EXIGE",
    "ACTO ABUSIVO",
    "OBLIGA A",
    "INCUMPLIMIENTO INJUSTIFICADO",
    "ELLA MISMA FIRMÓ",
    "AFECTA DIRECTAMENTE EL FLUJO DE RECURSOS",
    "CARECE DE SUSTENTO LEGAL",
    "NO FUE RESPETADA",
]

# Errores típicos de citación legal (incorrecto → correcto)
_CITAS_INCORRECTAS = [
    ("ART. 1601 ", "ART. 1602 "),
    ("ARTÍCULO 1601 ", "ART. 1602 "),
    ("ARTICULO 1601 ", "ART. 1602 "),
    ("LEY 1438 DE 2015", "LEY 1438 DE 2011"),
    ("RES. 2284 DE 2024", "RES. 2284 DE 2023"),
    ("RESOLUCIÓN 2284/2024", "RESOLUCIÓN 2284/2023"),
]

_EMAILS_CONTACTO = ("CARTERA@HUS.GOV.CO", "GLOSASYDEVOLUCIONES@HUS.GOV.CO")


def _extraer_argumento_xml(xml: str) -> Optional[str]:
    """Extrae el contenido de <argumento>...</argumento>."""
    if not xml:
        return None
    m = re.search(
        r"<argumento>(.*?)</argumento>", xml, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    return (m.group(1) or "").strip()


def detectar_defectos_criticos(
    dictamen_xml: str,
    *,
    codigo_glosa: str = "",
    valor_objetado: Optional[str] = None,
    tiene_contrato: bool = False,
    valor_facturado: Optional[str] = None,
) -> list[dict]:
    """Detecta defectos CRÍTICOS que justifican retry de la IA.

    Cada defecto retorna un dict con:
      regla: id corto
      mensaje: descripción legible
      sugerencia: cómo arreglarlo en el reintento

    Filosofía:
      - solo defectos que el LLM PUEDE corregir si se le indica
      - no incluye warnings "soft" (longitud, mayúsculas) que no
        afectan utilidad legal
      - resultado vacío [] significa que el dictamen es usable
    """
    defectos: list[dict] = []
    if not dictamen_xml or not dictamen_xml.strip():
        return [{
            "regla": "vacio",
            "mensaje": "La respuesta de la IA está vacía.",
            "sugerencia": "Genera el dictamen completo en el formato XML del contrato.",
        }]

    # 1. Tag <argumento> obligatorio
    arg = _extraer_argumento_xml(dictamen_xml)
    if arg is None:
        defectos.append({
            "regla": "sin_argumento",
            "mensaje": "Falta el tag <argumento>...</argumento>.",
            "sugerencia": (
                "Incluye obligatoriamente <argumento>...</argumento> "
                "con el dictamen completo en MAYÚSCULAS."
            ),
        })
        return defectos  # sin argumento, los demás checks no aplican

    if len(arg) < 80:
        defectos.append({
            "regla": "argumento_vacio",
            "mensaje": "El tag <argumento> tiene menos de 80 caracteres.",
            "sugerencia": "Redacta el dictamen completo según las reglas del system prompt.",
        })
        return defectos

    arg_up = arg.upper()

    # 2. Inicio obligatorio: el system prompt exige "ESE HUS NO ACEPTA"
    # como PRIMERAS palabras, sin antefijos como "RESPETUOSAMENTE".
    primeras = arg.strip()[:50].upper()
    if not primeras.startswith("ESE HUS NO ACEPTA"):
        defectos.append({
            "regla": "inicio_invalido",
            "mensaje": 'El dictamen no inicia con "ESE HUS NO ACEPTA".',
            "sugerencia": (
                'Comienza el primer párrafo: '
                '"ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE..."'
            ),
        })

    # 3. Email institucional de contacto
    if not any(e in arg_up for e in _EMAILS_CONTACTO):
        defectos.append({
            "regla": "sin_email_contacto",
            "mensaje": "El dictamen no incluye el email institucional de contacto.",
            "sugerencia": (
                "Cierra el último párrafo con: "
                "COMUNICACIONES: CARTERA@HUS.GOV.CO, "
                "GLOSASYDEVOLUCIONES@HUS.GOV.CO."
            ),
        })

    # 4. Frases prohibidas (registro hostil)
    for frase in _FRASES_PROHIBIDAS_CRITICAS:
        if frase in arg_up:
            defectos.append({
                "regla": f"frase_prohibida_{frase.lower().replace(' ', '_')[:30]}",
                "mensaje": f'Detectada frase prohibida: "{frase}".',
                "sugerencia": (
                    f'Reemplaza "{frase}" por una expresión institucional '
                    "conciliadora (ver system prompt §USA SIEMPRE)."
                ),
            })

    # 5. Citas legales con sintaxis incorrecta
    for incorrecto, correcto in _CITAS_INCORRECTAS:
        if incorrecto.upper() in arg_up:
            defectos.append({
                "regla": "cita_incorrecta",
                "mensaje": f'Cita normativa incorrecta: "{incorrecto.strip()}".',
                "sugerencia": f'Usa "{correcto.strip()}".',
            })

    # 6. Placeholders con corchetes
    if re.search(r"\$\s*\[[^\]]+\]", arg) or re.search(
        r"\[(VALOR|CIFRA|MONTO|PACIENTE|PACINTE|MEDICO|CUPS|CODIGO|FECHA|NOMBRE)\]",
        arg.upper(),
    ):
        defectos.append({
            "regla": "placeholder_corchete",
            "mensaje": "Hay placeholders sin reemplazar (corchetes [VALOR], $[X], etc.).",
            "sugerencia": (
                'Si no tienes el dato exacto, usa frases neutras: '
                '"EL VALOR INDICADO EN EL EXPEDIENTE", '
                '"PACIENTE IDENTIFICADO EN EXPEDIENTE", "MÉDICO TRATANTE".'
            ),
        })

    # 7. Código de glosa correcto debe aparecer
    if codigo_glosa and codigo_glosa not in ("", "N/A"):
        if codigo_glosa.upper() not in arg_up:
            defectos.append({
                "regla": "codigo_glosa_no_mencionado",
                "mensaje": (
                    f'El dictamen no menciona el código solicitado '
                    f'"{codigo_glosa}".'
                ),
                "sugerencia": (
                    f'Cita explícitamente "GLOSA {codigo_glosa}" '
                    "en el primer y último párrafo."
                ),
            })

    # 8. Si hay valor numérico exacto pedido, debe aparecer
    if valor_objetado and not str(valor_objetado).upper().startswith("EL VALOR"):
        digitos = re.sub(r"[^\d]", "", str(valor_objetado))
        if len(digitos) >= 4:
            arg_digitos = re.sub(r"[^\d]", "", arg)
            if digitos not in arg_digitos:
                defectos.append({
                    "regla": "valor_no_textual",
                    "mensaje": (
                        f'El valor objetado exacto "{valor_objetado}" '
                        "no aparece en el dictamen."
                    ),
                    "sugerencia": (
                        f"Incluye textualmente {valor_objetado} en el "
                        "primer párrafo."
                    ),
                })

    # 9. Anti-contradicción: "tarifa propia" + "contrato" cuando hay contrato.
    #    Si el caso tiene contrato vigente, decir "tarifa propia
    #    institucional" es contradictorio: la tarifa pactada nace del
    #    contrato, no es unilateral. (Feedback del usuario 27-abr-2026.)
    if tiene_contrato:
        menciona_propia = re.search(
            r"TARIFA\s+PROPIA(?:\s+INSTITUCIONAL)?", arg_up,
        )
        # 9a. Auto-contradicción dentro de la misma frase:
        #     "TARIFA PROPIA INSTITUCIONAL PACTADA" — "propia" implica
        #     fijación unilateral, "pactada" implica acuerdo bilateral.
        #     Esto NO requiere mencionar contrato a parte; ya es
        #     contradictorio en sí mismo.
        propia_pactada = re.search(
            r"TARIFA\s+PROPIA(?:\s+INSTITUCIONAL)?\s+PACTADA", arg_up,
        )
        # 9b. Mención de contrato en cualquier forma habitual.
        menciona_contrato = re.search(
            r"(?:EN\s+VIRTUD\s+DEL\s+CONTRATO|CONFORME\s+AL\s+CONTRATO|"
            r"CONTRATO\s+(?:N[OUÚ]MERO|No\.?|NRO\.?|VIGENTE|"
            r"INTERADMINISTRATIVO|SUSCRITO|CELEBRADO)|"
            r"CONTRATO\s+\d|CL[ÁA]USULA\s+CONTRACTUAL)",
            arg_up,
        )
        if propia_pactada or (menciona_propia and menciona_contrato):
            defectos.append({
                "regla": "tarifa_propia_con_contrato",
                "mensaje": (
                    'El dictamen menciona "TARIFA PROPIA" '
                    "junto al contrato, lo cual es CONTRADICTORIO: "
                    "si hay contrato, la tarifa es PACTADA, no propia."
                ),
                "sugerencia": (
                    'Reescribe usando exclusivamente "TARIFA PACTADA EN '
                    "EL CONTRATO No. [X]\". NUNCA escribas "
                    '"TARIFA PROPIA INSTITUCIONAL" cuando hay contrato; '
                    "tampoco lo combines con la palabra PACTADA: "
                    '"propia" implica fijación unilateral y "pactada" '
                    "implica acuerdo, no pueden coexistir. Si necesitas "
                    "referenciar la Resolución 054/2026, dilo como "
                    '"tarifas incorporadas al contrato a través de la '
                    'Resolución 054/2026".'
                ),
            })

    # 9c. Confusión "FACTURADO POR $X" donde $X = valor objetado.
    #     Es un error conceptual GRAVE: el valor facturado es lo que HUS
    #     cobró (ej. $247.663); el valor objetado es lo que la EPS dice
    #     que es excedente (ej. $168.563). El LLM tiende a confundirlos
    #     cuando solo recibe el valor objetado del input.
    #     Heurística: si el dictamen dice "FACTURAD[O|A] POR $X" Y ese
    #     mismo $X coincide con el valor_objetado del input, marcamos
    #     defecto. Solo aplica cuando ADEMÁS conocemos el valor_facturado
    #     real y es DISTINTO del objetado, o no lo conocemos pero el
    #     número exacto del objetado aparece como "facturado por".
    if valor_objetado and not str(valor_objetado).upper().startswith("EL VALOR"):
        digitos_obj = re.sub(r"[^\d]", "", str(valor_objetado))
        digitos_fact = (
            re.sub(r"[^\d]", "", str(valor_facturado))
            if valor_facturado else ""
        )
        # Solo activamos la regla si:
        #   - hay un número claro de valor_objetado (≥4 dígitos),
        #   - NO conocemos un valor_facturado distinto, o lo conocemos y
        #     es distinto del objetado (caso real).
        if len(digitos_obj) >= 4 and digitos_obj != digitos_fact:
            # Buscar "FACTURAD(O|A) POR ... $<digitos_obj>" tolerando
            # puntos/comas y palabras intermedias cortas.
            patron = (
                r"FACTURAD[OA]S?\s+POR\b[^.]{0,30}?"
                r"\$?\s*[\d.,]*"
                + r"".join([d for d in digitos_obj])
            )
            # construimos un patrón laxo: permitimos puntos como
            # separadores de miles entre dígitos.
            laxo = (
                r"FACTURAD[OA]S?\s+POR\b[^.\n]{0,40}?\$\s*"
                + r"[\.,]?".join(list(digitos_obj))
            )
            if re.search(laxo, arg_up):
                obj_clean = str(valor_objetado).lstrip("$").strip()
                defectos.append({
                    "regla": "facturado_es_objetado",
                    "mensaje": (
                        f'El dictamen dice "FACTURADO POR ${obj_clean}" '
                        f'pero ${obj_clean} es el VALOR OBJETADO '
                        "(lo que la EPS rechaza pagar), NO el valor que "
                        "HUS facturó. Son conceptos distintos."
                    ),
                    "sugerencia": (
                        'Reescribe el párrafo 1 usando: "RESPECTO DEL '
                        f'CUAL LA ENTIDAD PAGADORA OBJETA ${obj_clean}" '
                        "(sin la palabra FACTURADO antes del valor "
                        "objetado). Si conoces el valor facturado real, "
                        'úsalo así: "FACTURADO POR $[REAL], RESPECTO '
                        f'DEL CUAL OBJETA ${obj_clean}".'
                    ),
                })

    # 10. Anti-divagación: la respuesta excesivamente larga oculta el
    #     argumento central. Más de 340 palabras = retry. Subido de
    #     290 a 340 (27-abr-2026) porque retries solo por longitud
    #     casi nunca mejoraban y desperdiciaban ~$0.05 por llamada.
    n_palabras = _contar_palabras(arg)
    if n_palabras > 340:
        defectos.append({
            "regla": "demasiado_largo",
            "mensaje": (
                f"El argumento tiene {n_palabras} palabras: divaga "
                "y diluye el alegato. Máximo 320."
            ),
            "sugerencia": (
                "Compacta: una idea por oración, sin repetir código/EPS/"
                "servicio. Elimina conectores redundantes y suprime la "
                "segunda cita literal si hay dos. Objetivo: 190-240 "
                "palabras (caso complejo) o 130-180 (caso simple)."
            ),
        })

    return defectos


def construir_instruccion_retry(defectos: list[dict]) -> str:
    """Construye el bloque a anexar al user_prompt para el reintento.

    Reemplaza la respuesta anterior y le indica a la IA exactamente
    qué corregir.
    """
    if not defectos:
        return ""
    partes = [
        "",
        "═══ TU RESPUESTA ANTERIOR TUVO DEFECTOS CRÍTICOS — REGENERA EL DICTAMEN COMPLETO ═══",
        "",
        "Detectamos los siguientes problemas que DEBES corregir:",
        "",
    ]
    for i, d in enumerate(defectos, 1):
        partes.append(f"{i}. ❌ {d['mensaje']}")
        if d.get("sugerencia"):
            partes.append(f"   ✅ {d['sugerencia']}")
    partes.append("")
    partes.append(
        "Genera de nuevo el dictamen completo en el formato XML "
        "(<paciente>, <servicio>, <contrato>, <tarifa>, <normas_clave>, "
        "<argumento>) corrigiendo TODO lo anterior. Ningún texto fuera "
        "de los tags."
    )
    return "\n".join(partes)


def resumen_defectos(defectos: list[dict]) -> dict:
    """Para logging/observabilidad."""
    return {
        "total": len(defectos),
        "reglas": [d["regla"] for d in defectos],
    }
