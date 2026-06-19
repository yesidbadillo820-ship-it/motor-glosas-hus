"""Tests de regresión ronda 6 (16-jun-2026) — fixes F, G, H, I, J, K, L."""

import re

from app.services.contexto_contractual_enriquecido import (
    bloque_kits_normativos_especiales,
    bloque_multi_factura,
    detectar_contextos_clinicos_especiales,
    detectar_multi_factura,
)
from app.services.glosa_ia_prompts import CONTRATOS_HUS, contratos_ajenos_citados
from app.services.glosa_service import (
    _extraer_citas_inducidas_eps,
    _neutralizar_cups_falsos,
    _neutralizar_frases_absurdas,
    _normalizar_codigo_dictamen,
    _PROMPT_CACHE_VERSION,
)


# ── Fix F: citas inducidas con normas extranjeras ────────────────────
def test_fix_f_nom_mexicana_detectada():
    """Caso 12 Compensar — NOM-035-STPS-2018 con cita atribuida."""
    texto = (
        "Conforme a la NOM-035-STPS-2018 y la ISO 9001:2015 cláusula 8.5.1, "
        "que 'establecen que las IPS deberán certificar sus procesos antes "
        "de aplicar guías extranjeras', se reconoce únicamente 50%."
    )
    citas = _extraer_citas_inducidas_eps(texto)
    assert len(citas) >= 1
    assert any("NOM-035" in c or "NOM" in c for c in citas)


def test_fix_f_iso_9001_detectada():
    """ISO 9001:2015 con cita atribuida."""
    texto = "La ISO 9001:2015, que 'dispone la certificación obligatoria', aplica."
    citas = _extraer_citas_inducidas_eps(texto)
    assert any("ISO 9001" in c for c in citas)


def test_fix_f_convenio_oit_detectado():
    """Convenio 161 OIT con cita atribuida."""
    texto = "Conforme al Convenio 161 OIT que 'señala las obligaciones del empleador'."
    citas = _extraer_citas_inducidas_eps(texto)
    assert any("Convenio 161" in c for c in citas)


def test_fix_f_guia_aha_no_se_marca_sin_cita():
    """Guía AHA mencionada SIN comillas atribuidas no se detecta (false positive)."""
    texto = "La guía AHA 2024 establece criterios; aplicamos sus recomendaciones."
    citas = _extraer_citas_inducidas_eps(texto)
    assert all("AHA" not in c for c in citas)


# ── Fix G: regímenes especiales con notas mejoradas ──────────────────
def test_fix_g_fomag_nota_excluye_decreto_ley_1795():
    """FOMAG es Magisterio (Decreto 3752/2003), NO FFMM (DL 1795/2000)."""
    nota = CONTRATOS_HUS["FOMAG"]["nota"]
    assert "3752 de 2003" in nota
    assert "NO aplican" in nota
    assert "1795" in nota  # explícitamente excluido


def test_fix_g_arl_anadido_al_catalogo():
    """Régimen ARL ahora está catalogado con explicación de scope."""
    assert "ARL" in CONTRATOS_HUS
    nota = CONTRATOS_HUS["ARL"]["nota"]
    assert "embarazo" in nota.lower()
    assert "1295" in nota


def test_fix_g_ppl_nota_incluye_decreto_5159():
    """PPL nota actualizada con Decreto 5159/2010 + lineamiento TBC."""
    nota = CONTRATOS_HUS["PPL"]["nota"]
    assert "5159" in nota
    assert "tuberculosis" in nota.lower() or "tbc" in nota.lower()


# ── Fix H: kits normativos por contexto clínico ──────────────────────
def test_fix_h_kit_pediatrico_para_rn_prematuro():
    """Caso 11: RN prematuro 28 semanas dispara kit pediátrico."""
    texto = (
        "Recién nacido prematuro extremo de 28 semanas + 2 días, peso al nacer "
        "1.080 gramos, Apgar 4/7, displasia broncopulmonar grado III."
    )
    contextos = detectar_contextos_clinicos_especiales(texto)
    titulos = [t for t, _ in contextos]
    assert any("PEDIATR" in t or "NEONATAL" in t for t in titulos)
    bloque = bloque_kits_normativos_especiales(texto)
    assert "Ley 1438 de 2011 Art. 67" in bloque
    assert "Decreto 780 de 2016" in bloque


def test_fix_h_kit_trasplante_para_donante_vivo():
    """Caso 13: trasplante renal donante vivo dispara kit trasplantes."""
    texto = "Trasplante renal de DONANTE VIVO relacionado. ERC estadio V."
    contextos = detectar_contextos_clinicos_especiales(texto)
    titulos = [t for t, _ in contextos]
    assert any("TRASPLANTE" in t for t in titulos)
    bloque = bloque_kits_normativos_especiales(texto)
    assert "Decreto 2493 de 2004" in bloque
    assert "timoglobulina" in bloque.lower() or "rATG" in bloque.lower()


def test_fix_h_kit_mdr_tb_para_tbc_resistente():
    """Caso 10: MDR-TB dispara kit tuberculosis."""
    texto = "Tuberculosis pulmonar multirresistente (MDR-TB) confirmada."
    bloque = bloque_kits_normativos_especiales(texto)
    assert "Programa Nacional" in bloque
    assert "bedaquilina" in bloque.lower()


def test_fix_h_kit_preeclampsia_distingue_arl():
    """Caso 9: preeclampsia dispara kit que distingue ARL vs régimen común."""
    texto = "Hipertensión gestacional severa con preeclampsia y cesárea de emergencia."
    bloque = bloque_kits_normativos_especiales(texto)
    assert "ARL" in bloque
    assert "1295" in bloque
    assert "mecanismo causal" in bloque.lower() or "MECANISMO CAUSAL" in bloque


def test_fix_h_sin_contexto_especial_no_inyecta():
    """Glosa sin RN/trasplante/MDR/preeclampsia → bloque vacío."""
    texto = "Procedimiento ambulatorio sin complicaciones."
    assert bloque_kits_normativos_especiales(texto) == ""


# ── Fix I: código de glosa coherente ─────────────────────────────────
def test_fix_i_codigo_na_corregido_al_real():
    """Caso 9: 'CÓDIGO N/A' → corregido al código del input."""
    d = "GLOSA SOBRE EL CÓDIGO N/A INTERPUESTA POR FOMAG"
    r = _normalizar_codigo_dictamen(d, "DE0101")
    assert "DE0101" in r
    assert "N/A" not in r


def test_fix_i_codigo_numerico_corregido():
    """Caso 12: 'CÓDIGO 12345' → corregido al código del input."""
    d = "GLOSA SOBRE EL CÓDIGO 12345 INTERPUESTA POR LA ENTIDAD"
    r = _normalizar_codigo_dictamen(d, "CL0801")
    assert "CL0801" in r
    assert "12345" not in r


def test_fix_i_codigo_correcto_se_respeta():
    """Si el código del dictamen ya coincide → no cambia."""
    d = "GLOSA SOBRE EL CÓDIGO CL0801 INTERPUESTA"
    r = _normalizar_codigo_dictamen(d, "CL0801")
    assert r == d


def test_fix_i_codigo_real_sin_referencia_no_toca():
    """Si codigo_real es 'N/A', no hay referencia para validar."""
    d = "GLOSA SOBRE EL CÓDIGO 12345 INTERPUESTA"
    r = _normalizar_codigo_dictamen(d, "N/A")
    assert r == d


# ── Fix J: frases absurdas neutralizadas ─────────────────────────────
def test_fix_j_no_admite_rebatimiento_eliminado():
    """Caso 12: 'no admite rebatimiento' neutralizado."""
    d = "Esta respuesta es definitiva y no admite rebatimiento alguno. Solicitamos..."
    r = _neutralizar_frases_absurdas(d)
    assert "rebatimiento" not in r.lower()


def test_fix_j_cualquier_intento_improcedente_eliminado():
    """Caso 10: 'cualquier intento de rebatir improcedente' neutralizado."""
    d = (
        "Cláusula preventiva: cualquier intento de rebatir esta solicitud "
        "será considerado improcedente. En ese orden de ideas..."
    )
    r = _neutralizar_frases_absurdas(d)
    assert "improcedente" not in r or "rebatir" not in r.lower()


def test_fix_j_argumento_legitimo_no_se_toca():
    """Una glosa con argumento legal real (Art. X dice Y) NO se ve afectada."""
    d = "El Art. 168 Ley 100/1993 establece la cobertura de urgencias."
    r = _neutralizar_frases_absurdas(d)
    assert r == d


# ── Fix K: multi-factura detectada ───────────────────────────────────
def test_fix_k_caso13_tres_facturas_detectadas():
    """Caso 13: 3 facturas en una sola glosa."""
    texto = (
        "FACTURA HUS-2026-118800 — Valor: 95 millones de pesos\n"
        "CONCEPTO 1 — TA0201 — $61.000.000\n"
        "FACTURA HUS-2026-118801 — Valor: $58.500.000\n"
        "CONCEPTO 3 — ME0701 — $58.500.000\n"
        "FACTURA HUS-2026-118802 — Valor: $34.000.000\n"
    )
    facturas = detectar_multi_factura(texto)
    assert len(facturas) == 3
    bloque = bloque_multi_factura(texto)
    assert "3 facturas" in bloque
    assert "SECCIÓN por cada factura" in bloque


def test_fix_k_una_sola_factura_no_dispara():
    """1 factura no dispara el bloque multi-factura."""
    texto = "Factura HUS-2026-118800 — Valor: $95.000.000"
    assert detectar_multi_factura(texto) == []
    assert bloque_multi_factura(texto) == ""


# ── Fix L: factura confundida como código ────────────────────────────
def test_fix_l_glosa_seguido_de_factura_neutralizado():
    """Caso 13: 'GLOSA 118800' → 'la glosa aplicada'."""
    d = "Se solicita el levantamiento de la glosa 118800 y el reconocimiento integral."
    r = _neutralizar_cups_falsos(d)
    assert "118800" not in r
    assert "la glosa aplicada" in r


def test_fix_l_glosa_codigo_real_no_se_toca():
    """'GLOSA AU0301' (código real alfanumérico) NO se neutraliza."""
    d = "Se solicita el levantamiento de la glosa AU0301 y reconocimiento."
    r = _neutralizar_cups_falsos(d)
    assert "AU0301" in r


def test_fix_l_no_se_pisa_con_fechas_yyyymmdd():
    """Fix L coexiste con el fix de fechas (sin doble sustitución)."""
    d = "Código CUPS 20260511 y glosa 118800 en una sola frase."
    r = _neutralizar_cups_falsos(d)
    assert "20260511" not in r  # fix C original
    assert "118800" not in r  # fix L
    # No debe haber espacios dobles ni "el el procedimiento":
    assert not re.search(r"\b(el|la)\s+\1\b", r, flags=re.IGNORECASE)


# ── Cache version bumped ─────────────────────────────────────────────
def test_cache_version_r6_bumped():
    """La constante de versión se bumpeó (sigue subiendo en rondas
    posteriores, basta con que sea >= r6)."""
    assert _PROMPT_CACHE_VERSION.startswith("r")
    import re as _re

    m = _re.match(r"r(\d+)", _PROMPT_CACHE_VERSION)
    assert m is not None
    assert int(m.group(1)) >= 6


# ── Verificación catálogo: ACTA 1388 sigue catalogada (regresión r5) ─
def test_regresion_acta_1388_sigue_catalogada():
    """No se rompe el fix B de la ronda 5: ACTA 1388 → NUEVA EPS."""
    d = "TARIFA SOAT-20% ACTA DE NEGOCIACIÓN No. 1388 DE 2024"
    assert "1388 DE 2024" in contratos_ajenos_citados(d, "COOSALUD")
    assert contratos_ajenos_citados(d, "NUEVA EPS") == []
