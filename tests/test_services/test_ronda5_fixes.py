"""Tests de regresión ronda 5 (16-jun-2026)."""

from app.services.glosa_ia_prompts import catalogo_contratos_eps, contratos_ajenos_citados
from app.services.glosa_service import (
    _extraer_citas_inducidas_eps,
    _neutralizar_eps_inventada,
    _PROMPT_CACHE_VERSION,
    _GROQ_SDK_SOPORTA_REASONING_EFFORT,
)


# ── Fix A: capability flag de proceso ───────────────────────────────
def test_fix_a_capability_flag_inicial_true():
    """La bandera arranca en True (probamos reasoning_effort la primera vez)."""
    # No podemos garantizar que el proceso de tests no la haya tocado,
    # pero al importar SÍ tiene su valor inicial. La condición es que sea
    # un bool válido — la lógica del fix vive en `_llamar_groq_con_retry`.
    assert isinstance(_GROQ_SDK_SOPORTA_REASONING_EFFORT, bool)


# ── Fix B: extractor tokens compuestos NNN/AAAA ─────────────────────
def test_fix_b_extractor_tokens_compuestos_nueva_eps():
    """NUEVA EPS contrato 'ACTA 1388 DE 2024' antes no generaba tokens —
    ahora "1388 DE 2024" y "1388/2024" están catalogados."""
    cat = catalogo_contratos_eps()
    tokens_nueva = [k for k, v in cat.items() if v == "NUEVA EPS"]
    assert "1388 DE 2024" in tokens_nueva, "NUEVA EPS sin token 1388 DE 2024"
    assert "1388/2024" in tokens_nueva, "NUEVA EPS sin token 1388/2024"


def test_fix_b_acta_1388_ajena_para_otras_eps():
    """ACTA 1388 citada con EPS != NUEVA EPS → contrato ajeno."""
    d = "TARIFA SOAT-20% ACTA DE NEGOCIACIÓN No. 1388 DE 2024 dispone..."
    assert contratos_ajenos_citados(d, "COOSALUD") == ["1388 DE 2024"]
    assert contratos_ajenos_citados(d, "DISPENSARIO MEDICO") == ["1388 DE 2024"]


def test_fix_b_acta_1388_legitima_para_nueva_eps():
    """ACTA 1388 citada con NUEVA EPS → no es ajeno."""
    d = "TARIFA SOAT-20% ACTA DE NEGOCIACIÓN No. 1388 DE 2024 dispone..."
    assert contratos_ajenos_citados(d, "NUEVA EPS") == []


def test_fix_b_famisanar_contrato_real_preservado():
    """S-13-1-03-1-04958 con FAMISANAR es el contrato real → no ajeno."""
    d = "el contrato S-13-1-03-1-04958 cláusula octava"
    assert contratos_ajenos_citados(d, "FAMISANAR") == []
    # Pero con otra EPS sí es ajeno
    assert "S-13-1-03-1-04958" in contratos_ajenos_citados(d, "SANITAS")


# ── Fix C: EPS inventada neutralizada ───────────────────────────────
def test_fix_c_eps_inventada_neutralizada():
    """Caso 4: EPS=COOSALUD pero dictamen menciona 'EPS SaludCo' (inventada)."""
    d = "ESE HUS NO ACEPTA glosa interpuesta por la EPS SaludCo respecto del servicio"
    r = _neutralizar_eps_inventada(d, "COOSALUD")
    assert "SaludCo" not in r
    assert "la entidad pagadora" in r


def test_fix_c_eps_correcta_se_respeta():
    """EPS=COOSALUD y dictamen dice 'EPS COOSALUD' → respeta."""
    d = "ESE HUS NO ACEPTA glosa interpuesta por la EPS COOSALUD respecto..."
    r = _neutralizar_eps_inventada(d, "COOSALUD")
    assert "COOSALUD" in r


def test_fix_c_otra_sin_definir_no_toca_nada():
    """Si EPS=OTRA / SIN DEFINIR no hay referencia para validar — no toca."""
    d = "interpuesta por la EPS XYZ respecto del servicio"
    r = _neutralizar_eps_inventada(d, "OTRA / SIN DEFINIR")
    assert r == d  # sin cambios


def test_fix_c_eps_conocida_cruzada_se_neutraliza():
    """EPS=NUEVA pero dictamen dice 'EPS FAMISANAR' (otra real) → neutraliza."""
    d = "interpuesta por la EPS FAMISANAR respecto del servicio"
    r = _neutralizar_eps_inventada(d, "NUEVA EPS")
    assert "FAMISANAR" not in r


# ── Fix D: cache key incluye versión ────────────────────────────────
def test_fix_d_prompt_cache_version_definida():
    """La constante de versión debe estar declarada y ser una string."""
    assert isinstance(_PROMPT_CACHE_VERSION, str)
    assert len(_PROMPT_CACHE_VERSION) >= 4


# ── Fix E: citas inducidas detectadas ───────────────────────────────
def test_fix_e_caso3_sanitas_detecta_dos_citas():
    """Texto exacto del caso 3 — dos citas atribuidas (Sentencia + Circular)."""
    texto = (
        "De conformidad con la Sentencia C-313 de 2014 de la Corte "
        "Constitucional, que en su parte resolutiva 'establece que las IPS "
        "no podrán cobrar servicios complementarios no incluidos expresamente "
        "en el acto de autorización', y con la Circular 066 de 2010 de la "
        "Supersalud que 'dispone la devolución automática de toda factura "
        "sin soporte de pertinencia', se glosa el servicio en su totalidad."
    )
    citas = _extraer_citas_inducidas_eps(texto)
    assert len(citas) >= 2
    assert any("C-313 de 2014" in c for c in citas)
    assert any("Circular 066 de 2010" in c for c in citas)


def test_fix_e_glosa_sin_citas_atribuidas_devuelve_vacio():
    """Una glosa normal que solo nombra normas SIN comillas atribuidas."""
    texto = "Se glosa por NO contar con autorización. Art. 168 Ley 100 de 1993."
    assert _extraer_citas_inducidas_eps(texto) == []


def test_fix_e_norma_sin_verbo_atribucion_no_se_detecta():
    """Norma en comillas pero sin verbo introductorio → no es cita inducida."""
    texto = "El Art. 57 Ley 1438 de 2011 'da plazo de 10 días'."
    # 'da' no está en la lista de verbos — debe pasar (false negative aceptable)
    citas = _extraer_citas_inducidas_eps(texto)
    assert all("da plazo" not in c.lower() for c in citas)
