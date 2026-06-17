"""Tests ronda 8 — banco de respuestas HUS + Llama 4 Maverick."""

from app.services.banco_respuestas_hus import (
    BANCO_HUS,
    bloque_banco_respuestas,
    familia_de_codigo,
)


# ── Banco poblado con las 8 familias × 3 ejemplos ────────────────────
def test_banco_cubre_8_familias():
    """Las 8 familias principales del manual único están en el banco."""
    esperadas = {"AU", "TA", "SO", "CL", "ME", "IN", "CO", "FA"}
    assert set(BANCO_HUS.keys()) == esperadas


def test_banco_3_ejemplos_por_familia():
    """3 respuestas tipo por familia (consistencia del banco aportado)."""
    for fam, ejemplos in BANCO_HUS.items():
        assert len(ejemplos) == 3, f"{fam} tiene {len(ejemplos)} ejemplos, esperaba 3"


def test_banco_respuestas_son_sustanciales():
    """Cada respuesta tiene >= 600 chars (no son fragmentos)."""
    for fam, ejemplos in BANCO_HUS.items():
        for i, ej in enumerate(ejemplos):
            assert len(ej) >= 600, f"{fam} ejemplo {i + 1} corto ({len(ej)} chars)"


def test_banco_respuestas_arrancan_con_apertura_oficial():
    """Todas arrancan con la apertura del HUS."""
    for fam, ejemplos in BANCO_HUS.items():
        for i, ej in enumerate(ejemplos):
            assert ej.startswith("ESE HUS NO ACEPTA GLOSA"), (
                f"{fam} ejemplo {i + 1} no inicia con la apertura oficial"
            )


# ── Alias de familia ─────────────────────────────────────────────────
def test_familia_au_directo():
    assert familia_de_codigo("AU0301") == "AU"


def test_familia_pe_alias_a_cl():
    """PE (pertinencia) usa los few-shots de CL (clínico)."""
    assert familia_de_codigo("PE0801") == "CL"


def test_familia_de_alias_a_fa():
    """DE (devolución) usa los few-shots de FA (facturación)."""
    assert familia_de_codigo("DE0101") == "FA"


def test_familia_codigo_vacio_o_invalido():
    assert familia_de_codigo("") == ""
    assert familia_de_codigo("X") == ""


# ── Bloque inyectado al prompt ───────────────────────────────────────
def test_bloque_para_cl_caso12():
    """Caso 12 (CL0801): el bloque trae 2 ejemplos CL y aclara que no es copia."""
    b = bloque_banco_respuestas("CL0801", max_ejemplos=2)
    assert "BANCO DE RESPUESTAS DEL HUS" in b
    assert "CÓDIGO CL — CLÍNICO / PERTINENCIA" in b
    # 2 ejemplos
    assert b.count("— EJEMPLO ") == 2
    # Instrucción de NO copiar
    assert "NO LAS COPIES LITERALMENTE" in b or "no las copies" in b.lower()
    assert "punto de partida" in b.lower()


def test_bloque_para_de_usa_fa():
    """DE0101 (caso 9) saca los ejemplos de FA por alias."""
    b = bloque_banco_respuestas("DE0101", max_ejemplos=1)
    assert "CÓDIGO FA — FACTURACIÓN" in b
    assert "— EJEMPLO 1" in b


def test_bloque_codigo_sin_familia_devuelve_vacio():
    """Si el código no matchea ninguna familia, devuelve cadena vacía."""
    assert bloque_banco_respuestas("") == ""
    assert bloque_banco_respuestas("XX0000") == ""


def test_bloque_max_ejemplos_respeta_limite():
    """max_ejemplos limita la cantidad inyectada."""
    b1 = bloque_banco_respuestas("AU0301", max_ejemplos=1)
    b3 = bloque_banco_respuestas("AU0301", max_ejemplos=3)
    assert b1.count("— EJEMPLO ") == 1
    assert b3.count("— EJEMPLO ") == 3


# ── Llama 4 Maverick como modelo primario Groq ───────────────────────
def test_llama_4_maverick_como_primario():
    """ronda 8: el modelo primario Groq es Llama 4 Maverick."""
    from app.core.config import Settings

    s = Settings()
    assert s.groq_model == "meta-llama/llama-4-maverick-17b-128e-instruct"


def test_gpt_oss_baja_a_fallback_1():
    """gpt-oss-120b (el primario anterior) queda de fallback inmediato."""
    from app.core.config import Settings

    s = Settings()
    assert s.groq_model_fallback_1 == "openai/gpt-oss-120b"


def test_cadena_groq_tiene_4_modelos():
    """La cadena ahora tiene 4 modelos antes de saltar a Anthropic."""
    from app.core.config import Settings

    s = Settings()
    assert hasattr(s, "groq_model_fallback_3")
    assert s.groq_model_fallback_3 == "llama-3.3-70b-versatile"
