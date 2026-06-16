"""Tests de regresión ronda 7 (16-jun-2026) — fixes M, N, O, P, Q, R, S, T."""

from app.services.citation_verifier import verificar_citas
from app.services.glosa_service import (
    _PROMPT_CACHE_VERSION,
    _cerrar_truncamiento,
    _neutralizar_frases_absurdas,
    _normalizar_codigo_dictamen,
)
from app.services.multi_codigo import MAX_CODIGOS_DICTAMEN


# ── Fix M: códigos cortos (1-3 dígitos puros) ────────────────────────
def test_fix_m_codigo_001_corregido():
    """Caso 12: 'CÓDIGO 001' → corregido al código real."""
    d = "SOBRE EL CÓDIGO 001 INTERPUESTA POR COMPENSAR"
    r = _normalizar_codigo_dictamen(d, "CL0801")
    assert "001" not in r
    assert "CL0801" in r


def test_fix_m_codigo_12_corregido():
    """'CÓDIGO 12' → corregido."""
    d = "GLOSA SOBRE EL CÓDIGO 12 INTERPUESTA"
    r = _normalizar_codigo_dictamen(d, "AU0301")
    assert "AU0301" in r


def test_fix_m_codigo_real_5digitos_no_se_tocaria():
    """Si el código fuera 5 dígitos pero correspondiera al real codigo
    (raro, pero defensivo): se respeta."""
    d = "CÓDIGO 12345 (es el real)"
    # Si codigo_real es ese mismo número, debe respetarse
    r = _normalizar_codigo_dictamen(d, "12345")
    # codigo_real no es válido formato — debe degradar a no tocar
    # (pasa el guard de "isdigit" → corregir al real)
    assert "12345" in r


# ── Fix N: variantes de frases absurdas ──────────────────────────────
def test_fix_n_no_susceptible_de_impugnacion_neutralizado():
    """Caso 9 FOMAG ronda 6: 'no susceptible de nueva impugnación'."""
    d = (
        "EN LOS TÉRMINOS DE LAS PARTES ACUERDAN QUE EL PRESENTE DICTAMEN "
        "SERÁ NO SUSCEPTIBLE DE NUEVA IMPUGNACIÓN, SALVO ACUERDO ESCRITO. "
        "EN ESE ORDEN DE IDEAS..."
    )
    r = _neutralizar_frases_absurdas(d)
    assert "no susceptible de nueva impugnación" not in r.lower()
    assert "impugnación" not in r.lower() or "no susceptible" not in r.lower()


def test_fix_n_clausula_anti_rebatimiento_inventada_neutralizada():
    """Caso 9: 'CLÁUSULA 12 — ANTI-REBATIMIENTO' es invento."""
    d = (
        "Acordamos según La CLÁUSULA 12 – ANTI-REBATIMIENTO establece: "
        "no rebatible. Solicitamos levantamiento."
    )
    r = _neutralizar_frases_absurdas(d)
    assert "ANTI-REBATIMIENTO" not in r
    assert "ANTI‐REBATIMIENTO" not in r


def test_fix_n_argumento_real_intacto():
    """Una cláusula REAL del contrato (Cláusula octava SOAT-5%) no se toca."""
    d = "Conforme a la Cláusula 8 que establece la tarifa SOAT -5%."
    r = _neutralizar_frases_absurdas(d)
    assert r == d


# ── Fix Q: cap multi-código subido ────────────────────────────────────
def test_fix_q_cap_subido_a_5():
    """El cap default ahora es 5 (caso 13 con 4 conceptos + caso 6 con 5)."""
    assert MAX_CODIGOS_DICTAMEN == 5


# ── Fix R: Decreto-Ley con guión Unicode reconocido ──────────────────
def test_fix_r_decreto_ley_con_guion_unicode():
    """Caso 9 ronda 6: 'Decreto‑Ley 1295/1994' (guión U+2011) NO debe
    marcarse como 'Ley 1295/1994' inexistente."""
    # U+2011 NON-BREAKING HYPHEN entre "Decreto" y "Ley"
    dictamen_html = "<p>la ARL conforme al Decreto‑Ley 1295/1994 (origen laboral)</p>"
    r = verificar_citas(dictamen_html)
    # No debe aparecer "Ley 1295" en los issues
    citas_inexistentes = [i["cita"] for i in r["issues"] if i["tipo"] == "NORMA_INEXISTENTE"]
    assert all("Ley 1295" not in c for c in citas_inexistentes), (
        f"Decreto-Ley 1295 con guión Unicode marcado como Ley inexistente: {citas_inexistentes}"
    )


def test_fix_r_decreto_ley_con_guion_em_dash():
    """Variante con em-dash U+2014 entre 'Decreto' y 'Ley'."""
    dictamen_html = "<p>según el Decreto—Ley 1295/1994</p>"
    r = verificar_citas(dictamen_html)
    citas_inexistentes = [i["cita"] for i in r["issues"] if i["tipo"] == "NORMA_INEXISTENTE"]
    assert all("Ley 1295" not in c for c in citas_inexistentes)


def test_fix_r_ley_1295_sola_sigue_inexistente():
    """Regresión: si alguien cita 'Ley 1295/1994' SIN 'Decreto-' delante,
    debe seguir marcándose inexistente (esa Ley no existe)."""
    dictamen_html = "<p>La Ley 1295 de 1994 establece</p>"
    r = verificar_citas(dictamen_html)
    citas = [i["cita"] for i in r["issues"]]
    assert any("Ley 1295" in c for c in citas)


# ── Fix S: cierre de truncamiento ────────────────────────────────────
def test_fix_s_parentesis_sin_cerrar():
    """Caso 13: dictamen termina con '(ART. 2284/2023».' sin cerrar."""
    d = (
        "Esto se sustenta en la normativa. EN APLICACIÓN DEL PRINCIPIO "
        "DE AUTONOMÍA PROFESIONAL (ART. 2284/2023»."
    )
    r = _cerrar_truncamiento(d)
    # El paréntesis abierto debe estar cortado
    assert r.count("(") <= r.count(")")
    assert "Se solicita el levantamiento" in r


def test_fix_s_conector_colgado_que():
    """Frase termina con 'QUE' suelto → cortar y cerrar."""
    d = "El Art. 57 establece. El Decreto dispone que"
    r = _cerrar_truncamiento(d)
    assert not r.rstrip(".").endswith(" QUE")
    assert "Se solicita el levantamiento" in r


def test_fix_s_dictamen_completo_no_se_toca():
    """Dictamen bien cerrado no se modifica."""
    d = "ESE HUS no acepta la glosa. Se solicita el levantamiento."
    r = _cerrar_truncamiento(d)
    assert r == d


# ── Cache version bumped ─────────────────────────────────────────────
def test_cache_version_r7_bumped():
    """La constante de versión se actualizó a r7."""
    assert _PROMPT_CACHE_VERSION == "r7-20260616"


# ── Fix U: catálogo CONTRATOS_HUS ampliado con 3 entidades nuevas ────
def test_fix_u_compensar_catalogado():
    """Compensar entró al catálogo con su contrato real (CSS009-2024)."""
    from app.services.glosa_ia_prompts import CONTRATOS_HUS

    assert "COMPENSAR" in CONTRATOS_HUS
    nota = CONTRATOS_HUS["COMPENSAR"]["nota"]
    assert "CSS009-2024" in CONTRATOS_HUS["COMPENSAR"]["numero"]
    # Explicita exclusión de normas extranjeras (caso 12 NOM/ISO)
    assert "NOM" in nota or "ISO" in nota or "extranjeras" in nota.lower()


def test_fix_u_positiva_catalogado():
    """Positiva (ARL) catalogada con contrato 0525/2017 + Otrosí 03."""
    from app.services.glosa_ia_prompts import CONTRATOS_HUS

    assert "POSITIVA" in CONTRATOS_HUS
    nota = CONTRATOS_HUS["POSITIVA"]["nota"]
    assert "0525 DE 2017" in CONTRATOS_HUS["POSITIVA"]["numero"]
    assert "1295" in nota  # Decreto-Ley ARL
    assert "MECANISMO CAUSAL" in nota  # distinción ARL vs régimen común


def test_fix_u_aurora_catalogada():
    """Aurora (Cía Vida) catalogada con GID-ARL-0090."""
    from app.services.glosa_ia_prompts import CONTRATOS_HUS

    assert "AURORA" in CONTRATOS_HUS
    assert "GID-ARL-0090" in CONTRATOS_HUS["AURORA"]["numero"]


def test_fix_u_compensar_contrato_ajeno_si_lo_cita_otra_eps():
    """Caso 12 ronda 7: si DMBUG cita CSS009-2024 → contrato ajeno."""
    from app.services.glosa_ia_prompts import contratos_ajenos_citados

    d = "según el contrato CSS009-2024 las tarifas..."
    assert contratos_ajenos_citados(d, "DMBUG") == ["CSS009-2024"]
    assert contratos_ajenos_citados(d, "COMPENSAR") == []


def test_fix_u_aurora_contrato_ajeno():
    """Si FAMISANAR cita GID-ARL-0090 → ajeno."""
    from app.services.glosa_ia_prompts import contratos_ajenos_citados

    d = "contrato GID-ARL-0090 establece"
    assert contratos_ajenos_citados(d, "FAMISANAR") == ["GID-ARL-0090"]


def test_fix_u_catalogo_cubre_15_entidades_principales():
    """Total de EPSs/regímenes catalogados >= 15 (carga completa de
    contratos del 16-jun-2026)."""
    from app.services.glosa_ia_prompts import CONTRATOS_HUS

    assert len(CONTRATOS_HUS) >= 15
