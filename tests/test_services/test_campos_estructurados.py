"""Tests de la Mejora #3 — salida estructurada incremental.

Cubre las funciones puras del pipeline:
  - _parsear_campos_estructurados: extracción + JSON tolerante + cast de tipos
  - _limpiar_bloque_campos_estructurados: borrado del bloque del dictamen
  - _validar_campos_estructurados: cruce LLM-vs-determinista + decisión de skip
  - _normalizar_eps_para_match / casts tolerantes

Estas funciones son deterministas (sin LLM) y son la base de toda la
mejora. El flag GLOSA_CAMPOS_ESTRUCTURADOS no las afecta — solo controla
si se cablean al flujo de analizar().
"""

from __future__ import annotations

import pytest

from app.services.glosa_service import (
    _cast_bool_tolerante,
    _cast_lista_ints_tolerante,
    _cast_lista_strs_tolerante,
    _limpiar_bloque_campos_estructurados,
    _normalizar_eps_para_match,
    _parsear_campos_estructurados,
    _validar_campos_estructurados,
)


def _envelope(json_str: str, *, con_cierre: bool = True) -> str:
    """Arma un res_ia simulado: argumento + bloque estructurado."""
    cierre = "</CAMPOS_ESTRUCTURADOS>" if con_cierre else ""
    return (
        "<paciente>JUAN PEREZ</paciente>"
        "<servicio>HOSPITALIZACIÓN PSIQUIÁTRICA CON TMS</servicio>"
        "<contrato>CTR-2024-SALUDTOTAL-HUS</contrato>"
        "<argumento>El HUS rechaza la glosa por las razones expuestas.</argumento>"
        f"\n<CAMPOS_ESTRUCTURADOS>\n{json_str}\n{cierre}"
    )


# ── Parseo ───────────────────────────────────────────────────────────


def test_parsear_campos_estructurados_ok():
    """Bloque bien formado → dict con los 6 campos tipados."""
    js = """{
      "eps_efectiva": "SALUD TOTAL",
      "servicio_objetado": "HOSPITALIZACIÓN PSIQUIÁTRICA CON TMS",
      "contrato_citado": "CTR-2024-SALUDTOTAL-HUS",
      "clausulas_respondidas": [18],
      "sancion_rechazada": true,
      "subconceptos_refutados": ["sancion", "no-pbs", "remision"]
    }"""
    out = _parsear_campos_estructurados(_envelope(js))
    assert out is not None
    assert out["eps_efectiva"] == "SALUD TOTAL"
    assert out["servicio_objetado"] == "HOSPITALIZACIÓN PSIQUIÁTRICA CON TMS"
    assert out["contrato_citado"] == "CTR-2024-SALUDTOTAL-HUS"
    assert out["clausulas_respondidas"] == [18]
    assert out["sancion_rechazada"] is True
    assert out["subconceptos_refutados"] == ["sancion", "no-pbs", "remision"]


def test_parsear_sin_bloque_devuelve_none():
    """res_ia sin <CAMPOS_ESTRUCTURADOS> → None (degradación)."""
    res = "<argumento>Texto sin bloque estructurado.</argumento>"
    assert _parsear_campos_estructurados(res) is None


def test_parsear_json_roto_irreparable_devuelve_none():
    """Bloque con JSON inválido irreparable → None."""
    js = "{ esto no es json válido :: }"
    assert _parsear_campos_estructurados(_envelope(js)) is None


def test_parsear_truncado_sin_cierre_recupera():
    """Bloque sin </CAMPOS_ESTRUCTURADOS> (max_tokens) → fallback recupera."""
    js = '{"eps_efectiva": "ECOOPSOS", "clausulas_respondidas": [24]}'
    out = _parsear_campos_estructurados(_envelope(js, con_cierre=False))
    assert out is not None
    assert out["eps_efectiva"] == "ECOOPSOS"
    assert out["clausulas_respondidas"] == [24]


def test_parsear_comillas_tipograficas_y_coma_colgante():
    """Limpieza repara comillas “” y comas colgantes; json.loads pasa."""
    js = "{“eps_efectiva”: “MEDIMÁS”, “clausulas_respondidas”: [31,],}"
    out = _parsear_campos_estructurados(_envelope(js))
    assert out is not None
    assert out["eps_efectiva"] == "MEDIMÁS"
    assert out["clausulas_respondidas"] == [31]


def test_cast_tolerante_tipos():
    """clausulas ['24','31'] → [24,31]; sancion 'si' → True; basura → None."""
    js = """{
      "eps_efectiva": "SURA",
      "clausulas_respondidas": ["24", "31"],
      "sancion_rechazada": "si",
      "subconceptos_refutados": 12345
    }"""
    out = _parsear_campos_estructurados(_envelope(js))
    assert out is not None
    assert out["clausulas_respondidas"] == [24, 31]
    assert out["sancion_rechazada"] is True
    # subconceptos no es lista → None individual, no tumba el dict
    assert out["subconceptos_refutados"] is None
    assert out["eps_efectiva"] == "SURA"


def test_parsear_campo_ausente_es_none():
    """Si el LLM omite un campo, queda None sin romper el resto."""
    js = '{"eps_efectiva": "NUEVA EPS"}'
    out = _parsear_campos_estructurados(_envelope(js))
    assert out is not None
    assert out["eps_efectiva"] == "NUEVA EPS"
    assert out["contrato_citado"] is None
    assert out["clausulas_respondidas"] is None
    assert out["sancion_rechazada"] is None


# ── Casts unitarios ──────────────────────────────────────────────────


def test_cast_bool_tolerante():
    assert _cast_bool_tolerante(True) is True
    assert _cast_bool_tolerante("true") is True
    assert _cast_bool_tolerante("SÍ") is True
    assert _cast_bool_tolerante("1") is True
    assert _cast_bool_tolerante("no") is False
    assert _cast_bool_tolerante("false") is False
    assert _cast_bool_tolerante("quizás") is None
    assert _cast_bool_tolerante(None) is None


def test_cast_lista_ints_tolerante():
    assert _cast_lista_ints_tolerante([18, 24]) == [18, 24]
    assert _cast_lista_ints_tolerante(["18", "cláusula 24"]) == [18, 24]
    assert _cast_lista_ints_tolerante([]) == []
    assert _cast_lista_ints_tolerante("18") is None  # no es lista
    assert _cast_lista_ints_tolerante(None) is None


def test_cast_lista_strs_tolerante():
    assert _cast_lista_strs_tolerante(["a", "b"]) == ["a", "b"]
    assert _cast_lista_strs_tolerante(["a", "", "  "]) == ["a"]
    assert _cast_lista_strs_tolerante("a") is None
    assert _cast_lista_strs_tolerante(None) is None


# ── Limpieza del bloque del dictamen ─────────────────────────────────


def test_bloque_eliminado_del_texto():
    """El texto resultante NUNCA contiene 'CAMPOS_ESTRUCTURADOS'."""
    js = '{"eps_efectiva": "SALUD TOTAL"}'
    res = _envelope(js)
    limpio = _limpiar_bloque_campos_estructurados(res)
    assert "CAMPOS_ESTRUCTURADOS" not in limpio.upper()
    assert "SALUD TOTAL" not in limpio  # el JSON entero se fue
    assert "<argumento>" in limpio  # el resto se conserva


def test_bloque_eliminado_sin_cierre():
    """Aunque el bloque esté truncado (sin cierre), se borra completo."""
    js = '{"eps_efectiva": "ECOOPSOS", "contrato_citado": "CTR-'
    res = _envelope(js, con_cierre=False)
    limpio = _limpiar_bloque_campos_estructurados(res)
    assert "CAMPOS_ESTRUCTURADOS" not in limpio.upper()
    assert "ECOOPSOS" not in limpio


def test_limpiar_sin_bloque_es_noop():
    """Texto sin bloque → idéntico (no-op)."""
    res = "<argumento>Texto normal.</argumento>"
    assert _limpiar_bloque_campos_estructurados(res) == res


# ── Normalización EPS ────────────────────────────────────────────────


def test_normalizar_eps_para_match():
    assert _normalizar_eps_para_match("SALUD TOTAL EPS-S") == "SALUD TOTAL"
    assert _normalizar_eps_para_match("MEDIMÁS EPS-S (LIQUIDACIÓN)") == "MEDIMAS LIQUIDACION"
    assert _normalizar_eps_para_match("Coosalud S.A.S") == "COOSALUD"
    assert _normalizar_eps_para_match("") == ""


# ── Validación / decisión de skip ────────────────────────────────────


def test_validar_eps_coincide_permite_skip():
    """eps_efectiva del LLM == determinista → skip 'eps'."""
    campos = {"eps_efectiva": "SALUD TOTAL EPS"}
    det = {"eps_efectiva": "SALUD TOTAL"}
    r = _validar_campos_estructurados(campos, det)
    assert "eps" in r["saltar"]
    assert r["campos_finales"]["eps_efectiva"] == "SALUD TOTAL"  # verdad = determinista
    assert r["divergencias"] == []


def test_validar_eps_diverge_no_skip():
    """eps_efectiva del LLM != determinista → NO skip, divergencia logueada,
    valor final = determinista."""
    campos = {"eps_efectiva": "SALUD CO"}
    det = {"eps_efectiva": "SALUD TOTAL"}
    r = _validar_campos_estructurados(campos, det)
    assert "eps" not in r["saltar"]
    assert r["campos_finales"]["eps_efectiva"] == "SALUD TOTAL"
    assert any("eps" in d for d in r["divergencias"])


def test_validar_eps_generica_no_es_ancla():
    """Si el determinista es genérico ('OTRA / SIN DEFINIR'), nunca skip."""
    campos = {"eps_efectiva": "ALGO"}
    det = {"eps_efectiva": "OTRA / SIN DEFINIR"}
    r = _validar_campos_estructurados(campos, det)
    assert "eps" not in r["saltar"]


def test_validar_contrato_coincide_permite_skip():
    campos = {"contrato_citado": "CTR-2024-MEDIMAS-HUS"}
    det = {"contrato_citado": "CTR-2024-MEDIMAS-HUS"}
    r = _validar_campos_estructurados(campos, det)
    assert "contrato" in r["saltar"]
    assert r["campos_finales"]["contrato_citado"] == "CTR-2024-MEDIMAS-HUS"


def test_validar_contrato_sin_determinista_no_skip():
    """Si no hay contrato determinista, nunca skip (defensa en profundidad)."""
    campos = {"contrato_citado": "CTR-INVENTADO-999"}
    det = {"contrato_citado": None}
    r = _validar_campos_estructurados(campos, det)
    assert "contrato" not in r["saltar"]


def test_validar_servicio_valido_permite_skip():
    campos = {"servicio_objetado": "PROSTATECTOMÍA RADICAL ROBÓTICA"}
    det = {"servicio_valido": True}
    r = _validar_campos_estructurados(campos, det)
    assert "servicio" in r["saltar"]


def test_validar_servicio_invalido_no_skip():
    campos = {"servicio_objetado": "el procedimiento facturado según historia clínica"}
    det = {"servicio_valido": False}
    r = _validar_campos_estructurados(campos, det)
    assert "servicio" not in r["saltar"]


def test_validar_multicodigo_nunca_skip():
    """En multi-código, ningún skip aunque todo coincida."""
    campos = {
        "eps_efectiva": "SALUD TOTAL",
        "contrato_citado": "CTR-2024-SALUDTOTAL-HUS",
        "servicio_objetado": "TMS",
    }
    det = {
        "eps_efectiva": "SALUD TOTAL",
        "contrato_citado": "CTR-2024-SALUDTOTAL-HUS",
        "servicio_valido": True,
    }
    r = _validar_campos_estructurados(campos, det, multi_codigo=True)
    assert r["saltar"] == set()


def test_validar_sancion_divergencia():
    """Sanción detectada pero el LLM dice no-rechazada → divergencia."""
    campos = {"sancion_rechazada": False}
    det = {"sancion_detectada": True}
    r = _validar_campos_estructurados(campos, det)
    assert any("sancion" in d for d in r["divergencias"])
    # La sanción NUNCA está en saltar (es generación de contenido).
    assert "sancion" not in r["saltar"]


def test_validar_campos_llm_none_degrada():
    """Si no hubo bloque (None), no skip ni divergencias."""
    r = _validar_campos_estructurados(None, {"eps_efectiva": "SURA"})
    assert r["saltar"] == set()
    assert r["divergencias"] == []
    assert r["campos_finales"] == {}


# ── Constructores de prompt ──────────────────────────────────────────


def test_instruccion_campos_estructurados():
    from app.services.glosa_service import _instruccion_campos_estructurados

    txt = _instruccion_campos_estructurados()
    assert "<CAMPOS_ESTRUCTURADOS>" in txt
    assert "eps_efectiva" in txt and "contrato_citado" in txt
    assert "PROHIBIDO inventar" in txt
    # Debe dejar claro que va DESPUÉS de </argumento>
    assert "</argumento>" in txt


def test_bloque_campos_a_confirmar():
    from app.services.glosa_service import _bloque_campos_a_confirmar

    txt = _bloque_campos_a_confirmar(
        "SALUD TOTAL",
        "CTR-2024-SALUDTOTAL-HUS",
        [{"id": "sancion"}, {"id": "no-pbs"}],
    )
    assert "SALUD TOTAL" in txt
    assert "CTR-2024-SALUDTOTAL-HUS" in txt
    assert "sancion" in txt and "no-pbs" in txt


def test_bloque_campos_a_confirmar_sin_datos():
    """Sin contrato ni subconceptos, solo lista la EPS."""
    from app.services.glosa_service import _bloque_campos_a_confirmar

    txt = _bloque_campos_a_confirmar("SURA", None, [])
    assert "SURA" in txt
    assert "contrato_citado" not in txt


# ── Integración end-to-end (analizar con flag ON/OFF) ────────────────
#
# Patrón de stub de _llamar_ia tomado de test_multi_codigo.py: se
# reemplaza la llamada al LLM por un envelope sintético que incluye el
# bloque <CAMPOS_ESTRUCTURADOS>, y se fuerza el flag vía get_settings.

_GLOSA_TMS = (
    "SALUD TOTAL: Se objeta integralmente la atención: (1) la terapia TMS "
    "NO está en el PBS; (2) la hospitalización de 22 días excede lo "
    "pertinente; (3) no hubo autorización previa. SE APLICA SANCIÓN DEL 10% "
    "AL VALOR FACTURADO conforme a la Cláusula 18 del contrato "
    "CTR-2024-SALUDTOTAL-HUS."
)

_ENVELOPE_CON_BLOQUE = (
    "<paciente>JUAN PEREZ</paciente>"
    "<servicio>HOSPITALIZACIÓN PSIQUIÁTRICA CON TMS</servicio>"
    "<contrato>CTR-2024-SALUDTOTAL-HUS</contrato>"
    "<argumento>LA ESE HUS NO ACEPTA LA GLOSA. LOS SERVICIOS FUERON "
    "PRESTADOS, SOPORTADOS Y FACTURADOS CONFORME A LO PACTADO. LA TERAPIA "
    "DE ESTIMULACIÓN MAGNÉTICA TRANSCRANEAL CUENTA CON RESPALDO CLÍNICO. "
    "EN CONSECUENCIA, SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO "
    "INTEGRO DEL VALOR FACTURADO.</argumento>"
    "\n<CAMPOS_ESTRUCTURADOS>\n"
    '{"eps_efectiva":"SALUD TOTAL","servicio_objetado":"HOSPITALIZACIÓN '
    'PSIQUIÁTRICA CON TMS","contrato_citado":"CTR-2024-SALUDTOTAL-HUS",'
    '"clausulas_respondidas":[18],"sancion_rechazada":true,'
    '"subconceptos_refutados":["sancion","no-pbs","autorizacion"]}\n'
    "</CAMPOS_ESTRUCTURADOS>"
)


def _preparar_entorno_ce(monkeypatch):
    monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
    monkeypatch.delenv("QUALITY_GATE_ROLLOUT_PCT", raising=False)
    monkeypatch.delenv("TOOL_USE_HABILITADO", raising=False)
    monkeypatch.delenv("MULTI_AGENT_HABILITADO", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MULTI_CODIGO_DICTAMENES", raising=False)

    import app.services.dictamen_directo as dd
    import app.services.validador_dictamen as vd

    monkeypatch.setattr(vd, "detectar_defectos_criticos", lambda *a, **k: [])
    monkeypatch.setattr(dd, "puede_emitir_directo", lambda *a, **k: False)


def _set_flag(monkeypatch, valor: bool):
    """Fuerza settings.glosa_campos_estructurados sin tocar el resto."""
    from app.core import config

    real = config.get_settings()
    nuevo = real.model_copy(update={"glosa_campos_estructurados": valor})
    monkeypatch.setattr(config, "get_settings", lambda: nuevo)


def _stub_ia(monkeypatch, envelope: str):
    from app.services.glosa_service import GlosaService

    async def fake_llamar_ia(self, system, user, *a, **k):
        return (envelope, "stub-test")

    monkeypatch.setattr(GlosaService, "_llamar_ia", fake_llamar_ia)


def _servicio_ce():
    from app.services.glosa_service import GlosaService

    return GlosaService(groq_api_key=None, anthropic_api_key=None, primary_ai="groq")


def _data_ce():
    from app.models.schemas import GlosaInput

    return GlosaInput(
        eps="SALUD TOTAL",
        etapa="RESPUESTA A GLOSA",
        tabla_excel=_GLOSA_TMS,
        valor_aceptado="0",
    )


@pytest.mark.asyncio
async def test_e2e_flag_on_bloque_no_contamina_dictamen(monkeypatch):
    """Flag ON: el dictamen radicable NUNCA contiene 'CAMPOS_ESTRUCTURADOS'."""
    _preparar_entorno_ce(monkeypatch)
    _set_flag(monkeypatch, True)
    _stub_ia(monkeypatch, _ENVELOPE_CON_BLOQUE)

    resultado = await _servicio_ce().analizar(_data_ce())
    assert "CAMPOS_ESTRUCTURADOS" not in resultado.dictamen.upper()


@pytest.mark.asyncio
async def test_e2e_flag_on_campos_poblados(monkeypatch):
    """Flag ON: GlosaResult.campos_estructurados queda poblado y la verdad
    de EPS/contrato es la determinista."""
    _preparar_entorno_ce(monkeypatch)
    _set_flag(monkeypatch, True)
    _stub_ia(monkeypatch, _ENVELOPE_CON_BLOQUE)

    resultado = await _servicio_ce().analizar(_data_ce())
    ce = resultado.campos_estructurados
    assert ce is not None
    assert "SALUD TOTAL" in (ce.get("eps_efectiva") or "")
    assert ce.get("contrato_citado") == "CTR-2024-SALUDTOTAL-HUS"
    # servicio aislado válido → skip aplicado
    assert "servicio" in ce.get("_saltar", [])


@pytest.mark.asyncio
async def test_e2e_flag_off_campos_none(monkeypatch):
    """Flag OFF: campos_estructurados es None y el bloque (si llegara) se
    borra igual del dictamen (degradación elegante)."""
    _preparar_entorno_ce(monkeypatch)
    _set_flag(monkeypatch, False)
    _stub_ia(monkeypatch, _ENVELOPE_CON_BLOQUE)

    resultado = await _servicio_ce().analizar(_data_ce())
    assert resultado.campos_estructurados is None
    # El borrado del bloque es incondicional (seguridad del documento).
    assert "CAMPOS_ESTRUCTURADOS" not in resultado.dictamen.upper()


@pytest.mark.asyncio
async def test_e2e_flag_on_sin_bloque_degrada(monkeypatch):
    """Flag ON pero la IA no emitió bloque → campos None, dictamen intacto."""
    _preparar_entorno_ce(monkeypatch)
    _set_flag(monkeypatch, True)
    envelope_sin = (
        "<paciente>JUAN PEREZ</paciente>"
        "<servicio>HOSPITALIZACIÓN PSIQUIÁTRICA CON TMS</servicio>"
        "<argumento>LA ESE HUS NO ACEPTA LA GLOSA. LOS SERVICIOS FUERON "
        "PRESTADOS Y SOPORTADOS. SE SOLICITA EL LEVANTAMIENTO Y EL PAGO "
        "INTEGRO DEL VALOR FACTURADO.</argumento>"
    )
    _stub_ia(monkeypatch, envelope_sin)

    resultado = await _servicio_ce().analizar(_data_ce())
    assert resultado.campos_estructurados is None
    assert resultado.dictamen  # se produjo dictamen normal
