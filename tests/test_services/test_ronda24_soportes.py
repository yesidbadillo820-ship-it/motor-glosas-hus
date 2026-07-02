"""Ronda 24 / Fase 2 Soportes (jul-2026) — el motor deja de argumentar
a ciegas.

Tres problemas atacados:
  1. El texto OCR de los soportes se truncaba a 2000 chars en el caso
     "simple" (la mayoría del tráfico): la IA tenía la HC adjunta pero
     no la veía. Ahora 12K por defecto, tunable por env var.
  2. Sin soportes, el fallback viejo AFIRMABA "el registro clínico
     respalda la atención" — empujando a la IA a inventar respaldo
     clínico. Ahora es defensivo: prohíbe citar folios/hallazgos y
     redirige a contrato + norma.
  3. El detector REQUIERE_SOPORTES solo gateaba el lote batch; el flujo
     interactivo generaba en silencio. Ahora inyecta una ALERTA en el
     prompt con los soportes que faltan.

Además: multimodal_auto_activado() — PDF nativo automático SOLO para
casos ya escalados a Claude (sin convertir cada glosa en llamada cara).
"""

from __future__ import annotations

TEXTO_GLOSA_BASE = (
    "LA EPS OBJETA EL COBRO DEL SERVICIO PRESTADO POR CUANTO CONSIDERA "
    "QUE LA TARIFA APLICADA NO CORRESPONDE A LA PACTADA CONTRACTUALMENTE "
    "Y SOLICITA AJUSTE DEL VALOR FACTURADO."
)


def _limpiar_env(monkeypatch):
    monkeypatch.delenv("GLOSA_SOPORTES_MAX_CHARS_SIMPLE", raising=False)
    monkeypatch.delenv("GLOSA_SOPORTES_MAX_CHARS_COMPLEJO", raising=False)
    monkeypatch.delenv("GLOSA_MULTIMODAL_AUTO", raising=False)


# ─────────────────────────────────────────────────────────────────────
# 1. Tope de OCR: 2000 → 12000 por defecto, tunable por env
# ─────────────────────────────────────────────────────────────────────


def test_caso_simple_ya_no_trunca_a_2000(monkeypatch):
    """Marca a los ~8K chars del OCR debe llegar al prompt (antes moría
    en el corte de 2000)."""
    _limpiar_env(monkeypatch)
    from app.services.glosa_ia_prompts import build_user_prompt

    contexto = "X" * 8000 + " MARCA_OCHO_MIL " + "Y" * 11000 + " MARCA_VEINTE_MIL"
    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE,
        contexto,
        "TA0201",
        "COMPENSAR",
        valor_objetado="$150.000",
    )
    assert "MARCA_OCHO_MIL" in prompt, "el tope simple sigue en 2000 chars"
    assert "MARCA_VEINTE_MIL" not in prompt, "no se aplicó ningún tope"


def test_tope_simple_tunable_por_env(monkeypatch):
    _limpiar_env(monkeypatch)
    monkeypatch.setenv("GLOSA_SOPORTES_MAX_CHARS_SIMPLE", "3000")
    from app.services.glosa_ia_prompts import build_user_prompt

    contexto = "X" * 2500 + " MARCA_DOS_MIL_QUINIENTOS " + "Y" * 5000 + " MARCA_OCHO_MIL"
    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE,
        contexto,
        "TA0201",
        "COMPENSAR",
        valor_objetado="$150.000",
    )
    assert "MARCA_DOS_MIL_QUINIENTOS" in prompt
    assert "MARCA_OCHO_MIL" not in prompt, "la env var del tope no se respetó"


# ─────────────────────────────────────────────────────────────────────
# 2. Fallback sin soportes: defensivo, no invitación a alucinar
# ─────────────────────────────────────────────────────────────────────


def test_fallback_sin_soportes_es_defensivo(monkeypatch):
    """TA de valor bajo sin PDFs → fallback nuevo (prohíbe inventar),
    jamás el viejo 'EL REGISTRO CLÍNICO RESPALDA LA ATENCIÓN'."""
    _limpiar_env(monkeypatch)
    from app.services.glosa_ia_prompts import build_user_prompt

    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE,
        "",
        "TA0201",
        "COMPENSAR",
        valor_objetado="$150.000",
    )
    assert "PROHIBIDO citar folios" in prompt
    assert "RESPALDA LA ATENCIÓN PRESTADA" not in prompt


# ─────────────────────────────────────────────────────────────────────
# 3. Gate interactivo: ALERTA de expediente incompleto en el prompt
# ─────────────────────────────────────────────────────────────────────


def test_codigo_soportes_sin_pdfs_inyecta_alerta(monkeypatch):
    """SO* sin PDFs → la ALERTA entra al prompt con los soportes
    sugeridos por el detector (HC, RIPS, FEV...)."""
    _limpiar_env(monkeypatch)
    from app.services.glosa_ia_prompts import build_user_prompt

    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE,
        "",
        "SO3401",
        "COMPENSAR",
        valor_objetado="$150.000",
    )
    assert "ALERTA DE EXPEDIENTE INCOMPLETO" in prompt
    assert "Historia clínica institucional del paciente" in prompt


def test_pertinencia_sin_contexto_clinico_inyecta_alerta(monkeypatch):
    _limpiar_env(monkeypatch)
    from app.services.glosa_ia_prompts import build_user_prompt

    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE,
        "",
        "CL0301",
        "COMPENSAR",
        valor_objetado="$150.000",
    )
    assert "ALERTA DE EXPEDIENTE INCOMPLETO" in prompt


def test_alta_cuantia_sin_expediente_inyecta_alerta(monkeypatch):
    """>$2M sin PDFs → alerta (regla del coordinador, mayo-2026)."""
    _limpiar_env(monkeypatch)
    from app.services.glosa_ia_prompts import build_user_prompt

    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE,
        "",
        "TA0201",
        "COMPENSAR",
        valor_objetado="$5.000.000",
    )
    assert "ALERTA DE EXPEDIENTE INCOMPLETO" in prompt


def test_con_soportes_suficientes_no_hay_alerta(monkeypatch):
    """Con OCR real (>800 chars) el detector no corre y no hay alerta."""
    _limpiar_env(monkeypatch)
    from app.services.glosa_ia_prompts import build_user_prompt

    contexto = (
        "═══ DOCUMENTO: HISTORIA CLINICA ═══ Paciente con diagnóstico "
        "confirmado, evolución y plan de manejo documentados. " * 20
    )
    assert len(contexto) > 800
    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE,
        contexto,
        "SO3401",
        "COMPENSAR",
        valor_objetado="$150.000",
    )
    assert "ALERTA DE EXPEDIENTE INCOMPLETO" not in prompt


# ─────────────────────────────────────────────────────────────────────
# 4. Multimodal AUTO: solo para casos ya escalados a Claude
# ─────────────────────────────────────────────────────────────────────


def test_multimodal_auto_solo_en_casos_claude(monkeypatch):
    _limpiar_env(monkeypatch)
    from app.services.routing_complejidad import multimodal_auto_activado

    assert multimodal_auto_activado(True, None) is True
    assert multimodal_auto_activado(False, "claude-opus-4-7") is True
    # Caso simple (Groq/Haiku): NO se dispara — evita "siempre Claude".
    assert multimodal_auto_activado(False, None) is False
    assert multimodal_auto_activado(False, "claude-haiku-4-5-20251001") is False


def test_multimodal_auto_apagable_por_env(monkeypatch):
    _limpiar_env(monkeypatch)
    monkeypatch.setenv("GLOSA_MULTIMODAL_AUTO", "0")
    from app.services.routing_complejidad import multimodal_auto_activado

    assert multimodal_auto_activado(True, "claude-opus-4-7") is False
