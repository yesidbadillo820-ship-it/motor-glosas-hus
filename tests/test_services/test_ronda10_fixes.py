"""Tests de regresión ronda 10 (17-jun-2026) — fixes A, B, C, D.

Bugs detectados con corrida masiva real GLOSAS_17_JUNIO.xlsx (84 glosas
FAMISANAR/FOMAG/MUTUAL SER procesadas con Llama 4 Scout):

  A. QG contratos_fabricados: "VIGENTE", "ESTABLECE", "LEGALMENTE" se
     marcaban como números de contrato inventados → ESCALAR_HUMANO masivo.
  B. _neutralizar_eps_inventada: "LAS EPS RECONOCER LOS SERVICIOS" quedaba
     "LAS la entidad pagadora RECONOCER" (verbo tratado como EPS).
  C. _conector descomillar: en párrafo CAPS injecta "en los términos de"
     lowercase porque mira la cita, no el contexto huésped.
  D. recepcion_service: guardaba "C260043 - ENTIDAD PROMOTORA DE SALUD
     FAMISANAR S A S CONTRIBUTIVO" como eps. La IA copiaba esa cabecera
     verbosa al dictamen → ahora se normaliza a "FAMISANAR EPS".
"""

import re

from app.services.glosa_service import (
    _descomillar_citas_falsas,
    _neutralizar_eps_inventada,
    _PROMPT_CACHE_VERSION,
)
from app.services.quality_gate.post_validator import (
    check_contratos_no_fabricados,
)
from app.services.recepcion_service import _normalizar_eps_canonica


# ── Fix A: contratos_fabricados ─────────────────────────────────────
def test_fix_a_vigente_no_es_contrato_fabricado():
    """'CONTRATO VIGENTE' no debe marcarse como número fabricado."""
    dictamen = (
        "EL CONTRATO VIGENTE ENTRE LAS PARTES ESTABLECE UNA TARIFA "
        "PACTADA DE SOAT UVB VIGENTE CON UN DESCUENTO DEL 5%."
    )
    r = check_contratos_no_fabricados(dictamen, texto_glosa_input="glosa input")
    assert r.ok is True, f"Esperado ok=True, razón={r.razon}"


def test_fix_a_establece_no_es_contrato_fabricado():
    """'CONTRATO ESTABLECE' (regex glotonéa una palabra común)."""
    dictamen = "EL CONTRATO ESTABLECE LOS TÉRMINOS DE LA RELACIÓN COMERCIAL."
    r = check_contratos_no_fabricados(dictamen, texto_glosa_input="glosa input")
    assert r.ok is True


def test_fix_a_legalmente_no_es_contrato_fabricado():
    """'CONTRATO LEGALMENTE CELEBRADO' (frase del Art. 1602 C.C.)."""
    dictamen = (
        "CONFORME AL ART. 1602 DEL CÓDIGO CIVIL, TODO CONTRATO LEGALMENTE "
        "CELEBRADO ES UNA LEY PARA LOS CONTRATANTES."
    )
    r = check_contratos_no_fabricados(dictamen, texto_glosa_input="glosa input")
    assert r.ok is True


def test_fix_a_contrato_real_con_digitos_sigue_marcandose():
    """Número de contrato REAL fabricado (con dígitos) sigue detectándose."""
    dictamen = "EL CONTRATO S-99-9-99-9-99999 NO EXISTE EN EL INPUT."
    r = check_contratos_no_fabricados(dictamen, texto_glosa_input="otra cosa")
    assert r.ok is False
    assert "S-99-9-99-9-99999" in r.razon


def test_fix_a_contrato_real_en_input_se_respeta():
    """Si el número está en el input → no es fabricado."""
    dictamen = "EL CONTRATO 12076-359-2025 RIGE LAS PARTES."
    r = check_contratos_no_fabricados(
        dictamen, texto_glosa_input="contrato 12076-359-2025 firmado el ..."
    )
    assert r.ok is True


# ── Fix B: _neutralizar_eps_inventada con verbos ────────────────────
def test_fix_b_eps_seguido_de_verbo_no_se_neutraliza():
    """'LAS EPS RECONOCER LOS SERVICIOS' → no debe mutar a 'LAS la entidad
    pagadora RECONOCER LOS SERVICIOS'."""
    d = "ESTABLECE QUE LAS EPS RECONOCER LOS SERVICIOS PRESTADOS."
    r = _neutralizar_eps_inventada(d, "FAMISANAR")
    # El texto debe mantenerse intacto (no inyectó 'la entidad pagadora').
    assert "la entidad pagadora RECONOCER" not in r
    assert "LAS EPS RECONOCER" in r


def test_fix_b_eps_seguido_de_establece_no_se_neutraliza():
    """'EPS ESTABLECE' no debe verse como EPS=ESTABLECE."""
    d = "DEL CONTRATO, EPS ESTABLECE UNA TARIFA DISTINTA."
    r = _neutralizar_eps_inventada(d, "FAMISANAR")
    assert "EPS ESTABLECE" in r
    assert "la entidad pagadora ESTABLECE" not in r


def test_fix_b_eps_inventada_real_si_se_neutraliza():
    """Si la IA inventa una EPS real (no un verbo) → sí debe neutralizarse."""
    d = "ESE HUS NO ACEPTA glosa interpuesta por la EPS SaludCo respecto del servicio."
    r = _neutralizar_eps_inventada(d, "FAMISANAR")
    assert "SaludCo" not in r
    assert "LA ENTIDAD PAGADORA" in r.upper()  # el dictamen va en mayúsculas (05-08-2026)


def test_fix_b_eps_aplicar_no_se_neutraliza():
    """'EPS APLICAR' (verbo) → no debe neutralizarse."""
    d = "LA EPS APLICAR UNA TARIFA DISTINTA A LA PACTADA."
    r = _neutralizar_eps_inventada(d, "FAMISANAR")
    assert "LA EPS APLICAR" in r


# ── Fix C: descomillar respeta el contexto del párrafo huésped ──────
def test_fix_c_descomillar_en_parrafo_caps_usa_caps():
    """Cita mixed-case dentro de párrafo CAPS → conector en CAPS."""
    # Simulamos un issue de cita falsa con la huella exacta.
    cita = "Las partes acuerdan que cualquier modificación a las tarifas"
    contexto_caps = (
        "TAMBIÉN, SE INCUMPLE CON LA CLÁUSULA 5 DEL CONTRATO QUE ESTABLECE: "
        f"«{cita} pactadas deberá ser objeto de negociación previa.»"
    )
    issues = [{"tipo": "CITA_LITERAL_FALSA", "cita": cita}]
    r = _descomillar_citas_falsas(contexto_caps, issues)
    # En un párrafo CAPS el conector debe estar en CAPS también.
    assert "EN LOS TÉRMINOS DE" in r
    # No debe quedar la versión rota en minúsculas.
    assert "en los términos de Las partes" not in r


def test_fix_c_descomillar_en_parrafo_normal_usa_minuscula():
    """En párrafo normal mixed-case → conector en minúscula."""
    cita = "Las partes acuerdan que cualquier modificación a las tarifas"
    contexto_normal = (
        "También señalamos que la cláusula 5 del contrato establece: "
        f"«{cita} pactadas deberá ser objeto de negociación previa.»"
    )
    issues = [{"tipo": "CITA_LITERAL_FALSA", "cita": cita}]
    r = _descomillar_citas_falsas(contexto_normal, issues)
    assert "en los términos de" in r
    assert "EN LOS TÉRMINOS DE" not in r


# ── Fix D: normalización EPS Syscafe → corto canónico ────────────────
def test_fix_d_famisanar_contributivo_se_normaliza():
    """'C260043 - ENTIDAD PROMOTORA DE SALUD FAMISANAR S A S CONTRIBUTIVO'
    → 'FAMISANAR EPS' (no la cadena verbosa)."""
    r = _normalizar_eps_canonica(
        "C260043 - ENTIDAD PROMOTORA DE SALUD FAMISANAR S A S CONTRIBUTIVO"
    )
    assert r == "FAMISANAR EPS"


def test_fix_d_fomag_se_normaliza_aun_con_fideicomiso():
    """'U240061 - FIDEICOMISOS PATRIMONIOS AUTONOMOS FIDUCIARIA LA
    PREVISORA S.A.  FOMAG' → 'FOMAG'."""
    r = _normalizar_eps_canonica(
        "U240061 - FIDEICOMISOS PATRIMONIOS AUTONOMOS FIDUCIARIA LA PREVISORA S.A.  FOMAG"
    )
    assert r == "FOMAG"


def test_fix_d_mutual_ser_se_normaliza():
    r = _normalizar_eps_canonica("U220251 - MUTUAL SER EPS")
    assert r == "MUTUAL SER EPS"


def test_fix_d_clinica_chicamocha_se_reconoce():
    r = _normalizar_eps_canonica("U220361 - CLINICA CHICAMOCHA S.A.")
    assert r == "CLINICA CHICAMOCHA"


def test_fix_d_capital_salud_subsidiado_se_normaliza():
    r = _normalizar_eps_canonica(
        "U220332 - CAPITAL SALUD ENTIDAD PROMOTORA DE SALUD DEL REGIMEN SUBSIDIADO S.A.S."
    )
    assert r == "CAPITAL SALUD EPS"


def test_fix_d_eps_desconocida_devuelve_nombre_limpio():
    """Si no está en el catálogo, devuelve el nombre sin código Syscafe."""
    r = _normalizar_eps_canonica("X999999 - ENTIDAD XYZ EPS NUEVA SAS")
    # Debe quitar el código y dejar el nombre uppercase.
    assert r.startswith("ENTIDAD XYZ") or "XYZ" in r
    assert "X999999" not in r


def test_fix_d_entrada_vacia_devuelve_vacio():
    assert _normalizar_eps_canonica("") == ""


# ── Cache version bumped ────────────────────────────────────────────
def test_cache_version_r10_bumped():
    assert _PROMPT_CACHE_VERSION.startswith("r")
    m = re.match(r"r(\d+)", _PROMPT_CACHE_VERSION)
    assert m is not None
    assert int(m.group(1)) >= 10
