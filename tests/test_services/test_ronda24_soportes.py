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
    """TA de valor bajo sin PDFs → fallback nuevo (anti-invención con
    lenguaje SIEMPRE-verdadero), jamás el viejo 'EL REGISTRO CLÍNICO
    RESPALDA LA ATENCIÓN'."""
    _limpiar_env(monkeypatch)
    from app.services.glosa_ia_prompts import build_user_prompt

    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE,
        "",
        "TA0201",
        "COMPENSAR",
        valor_objetado="$150.000",
    )
    assert "NO inventes folios" in prompt
    assert "RESPALDA LA ATENCIÓN PRESTADA" not in prompt


def test_fallback_no_afirma_ausencia_de_documentos(monkeypatch):
    """Fix del review (ALTA-2): el fallback NO debe afirmar 'no hay
    documentos' ni 'PROHIBIDO citar folios' de forma absoluta — mentiría
    cuando los PDFs van adjuntos por multimodal en la misma llamada."""
    _limpiar_env(monkeypatch)
    from app.services.glosa_ia_prompts import build_user_prompt

    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE, "", "TA0201", "COMPENSAR", valor_objetado="$150.000"
    )
    assert "NO SE ADJUNTARON DOCUMENTOS COMPLEMENTARIOS" not in prompt
    assert "PROHIBIDO citar folios" not in prompt
    # Sí conserva la regla condicional siempre-verdadera:
    assert "APAREZCAN literalmente" in prompt


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
    assert "AVISO DE EXPEDIENTE" in prompt
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
    assert "AVISO DE EXPEDIENTE" in prompt


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
    assert "AVISO DE EXPEDIENTE" in prompt


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
    assert "AVISO DE EXPEDIENTE" not in prompt


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


# ─────────────────────────────────────────────────────────────────────
# 5. Fixes del review adversarial (jul-2026)
# ─────────────────────────────────────────────────────────────────────


def test_gate_no_apila_fallback_y_alerta(monkeypatch):
    """Dedup (BAJA-5): con contexto vacío + SO*, la ALERTA reemplaza al
    FALLBACK — no aparecen los dos (el FALLBACK 'SIN TEXTO OCR' se va)."""
    _limpiar_env(monkeypatch)
    from app.services.glosa_ia_prompts import build_user_prompt

    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE, "", "SO3401", "COMPENSAR", valor_objetado="$150.000"
    )
    assert "AVISO DE EXPEDIENTE" in prompt
    assert "SIN TEXTO OCR" not in prompt  # el FALLBACK no se apila


def test_gate_con_ocr_flaco_preserva_el_ocr(monkeypatch):
    """Con OCR real pero flaco (<800) + SO*, la ALERTA se antepone SIN
    pisar el texto OCR real."""
    _limpiar_env(monkeypatch)
    from app.services.glosa_ia_prompts import build_user_prompt

    prompt = build_user_prompt(
        TEXTO_GLOSA_BASE,
        "FOLIO_REAL_MARCA presente en el expediente.",
        "SO3401",
        "COMPENSAR",
        valor_objetado="$150.000",
    )
    assert "AVISO DE EXPEDIENTE" in prompt
    assert "FOLIO_REAL_MARCA" in prompt  # el OCR real se conserva


def test_multimodal_acepta_modelo_override():
    """Fix ALTA-1: la firma de _llamar_anthropic_multimodal acepta
    modelo_override (para no degradar Opus→Sonnet)."""
    import inspect

    from app.services.glosa_service import GlosaService

    sig = inspect.signature(GlosaService._llamar_anthropic_multimodal)
    assert "modelo_override" in sig.parameters


def test_backstop_caza_fuga_de_andamiaje_del_prompt():
    """Fix BAJA-6: si el modelo eco-ea el andamiaje del prompt al
    <argumento>, detectar_defectos_criticos lo marca (fuerza retry)."""
    from app.services.validador_dictamen import detectar_defectos_criticos

    xml = (
        "<paciente>X</paciente><servicio>Y</servicio>"
        "<argumento>ESE HUS NO ACEPTA LA GLOSA. AVISO DE EXPEDIENTE: "
        "NO INVENTES FOLIOS. Se solicita reconocimiento.</argumento>"
    )
    defectos = detectar_defectos_criticos(xml, codigo_glosa="SO3401")
    assert any(d["regla"] == "fuga_prompt_soportes" for d in defectos)


def test_backstop_no_marca_dictamen_limpio():
    """Un dictamen normal (sin andamiaje) NO dispara el backstop."""
    from app.services.validador_dictamen import detectar_defectos_criticos

    xml = (
        "<paciente>Juan</paciente><servicio>Artroplastia</servicio>"
        "<argumento>ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE TARIFA "
        "SOBRE EL CÓDIGO FACTURADO, DADO QUE LA TARIFA PACTADA CORRESPONDE "
        "AL SOAT MENOS DIEZ POR CIENTO CONFORME AL CONTRATO VIGENTE.</argumento>"
    )
    defectos = detectar_defectos_criticos(xml, codigo_glosa="TA0201")
    assert not any(d["regla"] == "fuga_prompt_soportes" for d in defectos)
