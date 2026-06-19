"""Tests ronda 9 (17-jun-2026) — fixes A, B, C, D."""

from app.services.contexto_contractual_enriquecido import detectar_contextos_clinicos_especiales
from app.services.glosa_service import (
    _extraer_citas_inducidas_eps,
    _neutralizar_placeholders_template,
)


# ── Fix A: placeholders del template ─────────────────────────────────
def test_fix_a_placeholders_caso14_neutralizados():
    """Caso 14 ronda 8: Llama 4 Scout dejó '$X', 'CÓDIGO YX', 'PACIENTE Z'
    literal del esqueleto del prompt en el dictamen entregado."""
    d = (
        "ESE HUS NO ACEPTA LA GLOSA APLICADA SOBRE EL CÓDIGO CL0801, "
        "RESPECTO DEL SERVICIO FACTURADO POR $X, CUYO CÓDIGO CUPS ES YX, "
        "PRESTADO AL PACIENTE Z."
    )
    r = _neutralizar_placeholders_template(d)
    # Los 3 placeholders desaparecieron
    assert "$X" not in r
    assert "CÓDIGO CUPS ES YX" not in r
    assert "PACIENTE Z" not in r
    # Las frases neutras del estilo HUS aparecen
    assert "valor objetado" in r.lower()
    assert "el paciente" in r.lower()


def test_fix_a_no_toca_codigos_reales():
    """Códigos REALES (AU0301, CL0801, etc.) no se tocan."""
    d = "SOBRE EL CÓDIGO AU0301 INTERPUESTA POR COOSALUD"
    r = _neutralizar_placeholders_template(d)
    assert r == d


def test_fix_a_no_toca_valor_real():
    """Valor REAL ($89.200.000) no se toca."""
    d = "facturado por $89.200.000 correspondiente"
    r = _neutralizar_placeholders_template(d)
    assert r == d


def test_fix_a_facturado_por_X_pesos():
    """'facturado por X PESOS' variante (Llama 4 sin $)."""
    d = "El procedimiento facturado por X pesos cuyo código"
    r = _neutralizar_placeholders_template(d)
    assert "facturado por X pesos" not in r.lower()
    assert "valor objetado" in r.lower()


# ── Fix B: kit trasplantes estricto ──────────────────────────────────
def test_fix_b_hemodialisis_cronica_sin_trasplante_no_dispara_kit():
    """Caso 16 ronda 8: ERC V con hemodiálisis crónica SIN trasplante NO
    debe disparar el kit TRASPLANTE (que cita Decreto 2493/2004)."""
    texto = (
        "Enfermedad renal crónica estadio V por nefropatía diabética. "
        "156 sesiones de hemodiálisis. Fístula arteriovenosa."
    )
    contextos = detectar_contextos_clinicos_especiales(texto)
    titulos = [t for t, _ in contextos]
    assert all("TRASPLANTE" not in t for t in titulos), (
        f"Hemodiálisis crónica sin trasplante NO debe disparar kit trasplante: {titulos}"
    )


def test_fix_b_trasplante_renal_real_si_dispara_kit():
    """Caso 13 ronda 6: trasplante renal donante vivo SÍ dispara kit."""
    texto = "Trasplante renal de DONANTE VIVO relacionado. ERC estadio V."
    contextos = detectar_contextos_clinicos_especiales(texto)
    titulos = [t for t, _ in contextos]
    assert any("TRASPLANTE" in t for t in titulos)


def test_fix_b_donante_vivo_solo_dispara_kit():
    """DONANTE VIVO sin la palabra 'trasplante' explícita: dispara kit."""
    texto = "Receptor de donante vivo relacionado. HLA idéntica 6/6."
    contextos = detectar_contextos_clinicos_especiales(texto)
    titulos = [t for t, _ in contextos]
    assert any("TRASPLANTE" in t for t in titulos)


# ── Fix C: citas inducidas extranjeras clínicas ──────────────────────
def test_fix_c_oms_guidelines_detectada():
    """Caso 17 ronda 8: 'OMS Guidelines on Hip Fracture Care 2024'."""
    texto = (
        "Conforme a las OMS Guidelines on Hip Fracture Care 2024, que "
        "'disponen que las cirugías deben realizarse en máximo 24 horas'."
    )
    citas = _extraer_citas_inducidas_eps(texto)
    assert any("OMS" in c for c in citas)


def test_fix_c_manual_merck_detectado():
    """'Manual MERCK Edition 2025' como cita inducida."""
    texto = "Al Manual MERCK Edition 2025 que 'establece las indicaciones'."
    citas = _extraer_citas_inducidas_eps(texto)
    assert any("MERCK" in c for c in citas)


def test_fix_c_jci_standards_detectado():
    """'JCI Standards for Hospital Accreditation' como cita inducida."""
    texto = (
        "Según los Standards JCI International for Hospital Accreditation "
        "6th Edition, que 'ordenan documentar el tiempo quirúrgico'."
    )
    citas = _extraer_citas_inducidas_eps(texto)
    assert any("JCI" in c for c in citas)


def test_fix_c_resolucion_colombiana_real_tambien_se_atrapa():
    """Regresión: las normas colombianas reales siguen detectándose."""
    texto = (
        "Conforme a la Resolución 2335 de 2023 en su artículo 8, "
        "que 'dispone que la EPS tiene derecho a glosar'."
    )
    citas = _extraer_citas_inducidas_eps(texto)
    assert any("Resolución 2335" in c for c in citas)
