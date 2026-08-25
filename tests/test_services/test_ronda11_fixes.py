"""Tests de regresión ronda 11 (18-jun-2026) — fix alucinaciones del prompt.

Evidencia (FAMISANAR HUS, Llama 4 Scout, 18-jun):
  CO0701 (TRAMADOL AMP $1.800) → dictamen alucinado:
    "FACTURADO POR $100.000"     ← valor real $1.800
    "CUPS 1234"                  ← real 19997313-6
    "GLOSA 12345"                ← inventado
    "RESOLUCIÓN 2641 DE 2024"    ← norma inexistente
    "REALIZADO EL 10 DE ENERO DE 2023" ← fecha inventada
  CO0601 (CATÉTER $5.800) → mismo patrón.

Causa raíz: las reglas anti-alucinación del system prompt mostraban esos
valores como EJEMPLOS prohibidos (anti-patrón clásico). La IA los copiaba
textualmente. El fix es doble:
  A. Reescribir las reglas para NO mostrar los ejemplos.
  B. Red final que neutraliza los placeholders si aún aparecen.
"""

import re

from app.services.glosa_ia_prompts import SYSTEM_BASE
from app.services.glosa_service import (
    _PROMPT_CACHE_VERSION,
    _neutralizar_alucinaciones_prompt,
)


# ── Fix A: el prompt NO contiene las semillas alucinables ────────────
def test_system_prompt_no_contiene_dollar_1000000():
    assert "$1000000" not in SYSTEM_BASE
    assert "$1.000.000" not in SYSTEM_BASE
    assert "$100.000" not in SYSTEM_BASE


def test_system_prompt_no_contiene_cups_1234():
    assert "CUPS 1234" not in SYSTEM_BASE
    assert "cups 1234" not in SYSTEM_BASE.lower() or "cups 12345" in SYSTEM_BASE.lower()


def test_el_prompt_no_ensena_la_2641_como_ejemplo_de_lo_prohibido():
    """El prompt no debe mostrar el numero como ejemplo de norma prohibida.

    Esta regla sigue en pie y por la misma razon de siempre: cuando las reglas
    anti-alucinacion mostraban «Resolucion 2641 de 2024» como EJEMPLO de lo
    prohibido, la IA la copiaba al dictamen sin venir al caso.

    Lo que SI cambio (25-08-2026): se creia que esa resolucion era inventada, y
    el motor la borraba del dictamen. No lo es. Verificada contra la fuente
    oficial, es la Resolucion 2641 del 23 de diciembre de 2024, la que
    establecio la CUPS que rigio durante 2025. El motor estaba borrando una
    cita correcta y dejando en su lugar una frase sin ley ni articulo. Ese
    borrado se retiro; esta regla del prompt no.
    """
    import re

    for m in re.finditer(r"2641\s*[/ ]\s*(?:DE\s*)?2024", SYSTEM_BASE, re.IGNORECASE):
        vecindad = SYSTEM_BASE[max(0, m.start() - 220) : m.end() + 220].lower()
        for palabra in ("prohibid", "inventad", "no cites", "nunca cites", "alucin"):
            assert palabra not in vecindad, (
                "el prompt volvió a mostrar la Resolución 2641 de 2024 como ejemplo de "
                f"norma prohibida (aparece cerca de «{palabra}»); la IA copia lo que ve"
            )


# ── Fix B: red final neutraliza los placeholders del dictamen ────────
def test_neutraliza_valor_100000_falso():
    """'FACTURADO POR $100.000' → frase neutra."""
    d = "ESE HUS NO ACEPTA LA GLOSA. SERVICIO FACTURADO POR $100.000."
    r = _neutralizar_alucinaciones_prompt(d)
    assert "$100.000" not in r
    # 06-08-2026: el sintagma neutro pasó a MAYÚSCULA sostenida, como todo
    # el dictamen. Antes salía en minúscula dentro de un texto en caps y el
    # documento se veía pegado de dos pedazos.
    assert "EL VALOR OBJETADO CONSIGNADO EN EL EXPEDIENTE" in r.upper()


def test_neutraliza_valor_1000000_falso():
    d = "FACTURADO POR $1.000.000 EN ATENCIÓN MÉDICA."
    r = _neutralizar_alucinaciones_prompt(d)
    assert "$1.000.000" not in r
    # 06-08-2026: el sintagma neutro pasó a MAYÚSCULA sostenida, como todo
    # el dictamen. Antes salía en minúscula dentro de un texto en caps y el
    # documento se veía pegado de dos pedazos.
    assert "EL VALOR OBJETADO CONSIGNADO EN EL EXPEDIENTE" in r.upper()


def test_neutraliza_cups_1234():
    d = "EL PROCEDIMIENTO QUIRÚRGICO CON CUPS 1234 REALIZADO EN URGENCIAS."
    r = _neutralizar_alucinaciones_prompt(d)
    assert "CUPS 1234" not in r
    # 06-08-2026: el sintagma neutro pasó a MAYÚSCULA sostenida, como todo
    # el dictamen. Antes salía en minúscula dentro de un texto en caps y el
    # documento se veía pegado de dos pedazos.
    assert "EL CUPS DE LA FACTURA" in r.upper()


def test_neutraliza_codigo_cups_1234():
    d = "REFERENTE AL CÓDIGO CUPS 1234 DEL PROCEDIMIENTO."
    r = _neutralizar_alucinaciones_prompt(d)
    assert "CUPS 1234" not in r


def test_no_neutraliza_cups_reales():
    """Los CUPS reales (alfanuméricos como FMQ0113) NO deben tocarse.

    Ronda 15 (25-jun-2026): el código "19997313-6" tipificado en ronda 11
    como "CUPS válido del catálogo HUS" en realidad es un CUM (Código
    Único de Medicamento, formato 8 dígitos + verificador). La IA usaba
    ese código mal nombrado como "CUPS" — el caso real es alucinación
    de categorización: TRAMADOL es medicamento, su código correcto es
    CUM, no CUPS. El sanitizer ronda 15 ahora lo neutraliza con la
    frase "el medicamento facturado..." cuando aparece como "CUPS X-Y".
    Los CUPS REALES alfanuméricos (FMQ0113 = catéter) siguen intactos.
    """
    d = "EL CUPS 19997313-6 (TRAMADOL) Y EL CUPS FMQ0113 (CATÉTER)."
    r = _neutralizar_alucinaciones_prompt(d)
    # CUM mal nombrado como CUPS → neutralizado por ronda 15 Bug A v4
    assert "19997313-6" not in r
    assert "el medicamento facturado" in r.lower()
    # CUPS real alfanumérico → preservado
    assert "FMQ0113" in r


def test_neutraliza_glosa_12345():
    d = "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA 12345 Y EL PAGO ÍNTEGRO."
    r = _neutralizar_alucinaciones_prompt(d)
    assert "GLOSA 12345" not in r
    assert "la glosa aplicada" in r.lower() or "LA GLOSA APLICADA" in r


def test_ya_no_se_borra_la_resolucion_2641_de_2024():
    """La Resolución 2641 de 2024 NO era inventada.

    Estas pruebas exigían que el motor la borrara del dictamen. Se creía
    inventada porque el prompt la usaba como EJEMPLO de norma prohibida y la IA
    la copiaba. Al verificarla el 25-08-2026 contra la fuente oficial resultó
    REAL: es la Resolución 2641 del 23 de diciembre de 2024, la que estableció
    la CUPS que rigió durante 2025.

    O sea que el motor borraba la cita CORRECTA y en su lugar dejaba «la
    normativa vigente del Ministerio de Salud» — una frase sin ley, decreto ni
    artículo, justo la clase de pseudo-norma que la auditoría independiente
    reprochó. Se retiró esa neutralización.

    Hoy esa resolución está derogada (la Res. 2706 de 2025 la reemplazó desde el
    1 de enero de 2026), y de eso avisa el verificador de citas, que ahora sí
    mira la vigencia. Avisar no es lo mismo que borrar: para un servicio
    prestado en 2025 citarla es lo correcto.
    """
    d = "LA RESOLUCIÓN 2641 DE 2024 DEL MINISTERIO DE SALUD ESTABLECE..."
    r = _neutralizar_alucinaciones_prompt(d)
    assert "2641 DE 2024" in r.upper(), "se volvió a borrar una cita correcta"
    assert "NORMATIVA VIGENTE DEL MINISTERIO" not in r.upper()


def test_neutraliza_historia_clinica_1234567():
    d = "CONFORME A LA HISTORIA CLÍNICA N° 1234567 SUSCRITA POR EL DR. X."
    r = _neutralizar_alucinaciones_prompt(d)
    assert "1234567" not in r


def test_neutraliza_fecha_10_enero_2023():
    d = "EL PROCEDIMIENTO REALIZADO EL 10 DE ENERO DE 2023 SEGÚN EXPEDIENTE."
    r = _neutralizar_alucinaciones_prompt(d)
    assert "10 DE ENERO DE 2023" not in r
    assert "10 de enero de 2023" not in r


def test_neutraliza_no_toca_valores_legitimos():
    """Valores reales NO redondos deben pasar intactos."""
    d = "FACTURADO POR $1.800 EL TRAMADOL Y $5.800 EL CATÉTER FMQ0113."
    r = _neutralizar_alucinaciones_prompt(d)
    assert r == d  # sin cambios


def test_neutraliza_idempotente():
    """Aplicar la red dos veces da el mismo resultado."""
    d = "FACTURADO POR $100.000 CON CUPS 1234 SEGÚN RESOLUCIÓN 2641 DE 2024."
    r1 = _neutralizar_alucinaciones_prompt(d)
    r2 = _neutralizar_alucinaciones_prompt(r1)
    assert r1 == r2


# ── Cache bumpeado ──────────────────────────────────────────────────
def test_cache_version_r11_bumped():
    m = re.match(r"r(\d+)", _PROMPT_CACHE_VERSION)
    assert m is not None
    assert int(m.group(1)) >= 11
