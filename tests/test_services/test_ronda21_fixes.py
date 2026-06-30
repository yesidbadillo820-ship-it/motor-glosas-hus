"""Tests de regresión ronda 21 (30-jun-2026) — auditoría del dictamen
MEDIMÁS da Vinci $273M en producción.

Caso real: la glosa cita textualmente el contrato CTR-2024-MEDIMAS-HUS
con tarifa SOAT × 0.85, pero el dictamen producido decía DOS veces "al no
existir contrato pactado" — auto-contradicción legal-killer: el campo
"Contrato:" quedó corregido pero el cuerpo negaba el contrato citado por
la EPS.

Bug #1 — _reescribir_negacion_contrato no cubría la forma verbal
"(al) no existir contrato pactado" (solo "SIN/NO EXISTE CONTRATO
PACTADO"). El infinitivo/conjugado se escapaba.
"""

from __future__ import annotations

import pytest

from app.services.glosa_service import _reescribir_negacion_contrato

_GLOSA_MEDIMAS = (
    "(III) TARIFA: el contrato vigente CTR-2024-MEDIMAS-HUS define para "
    "prostatectomía CUPS 60.1.2.01 una tarifa de SOAT × 0.85."
)


class TestBug1NegacionContratoInfinitivo:
    def test_al_no_existir_contrato_pactado_se_reescribe(self):
        """La frase real del dictamen MEDIMÁS (1ª ocurrencia)."""
        d = (
            "facturado bajo tarifa SOAT pleno conforme al manual tarifario "
            "SOAT 2026 vigente, al no existir contrato pactado con la entidad."
        )
        out = _reescribir_negacion_contrato(d, texto_glosa=_GLOSA_MEDIMAS)
        assert "al no existir contrato pactado" not in out.lower()
        assert "CTR-2024-MEDIMAS-HUS" in out

    def test_al_no_existir_contrato_pactado_segunda_ocurrencia(self):
        """2ª ocurrencia: la que funda toda la defensa tarifaria."""
        d = (
            "En tercer lugar, al no existir contrato pactado rige el manual "
            "tarifario SOAT 2026 en su integridad conforme al art. 177."
        )
        out = _reescribir_negacion_contrato(d, texto_glosa=_GLOSA_MEDIMAS)
        assert "al no existir contrato pactado" not in out.lower()
        assert "CTR-2024-MEDIMAS-HUS" in out

    def test_variantes_verbales(self):
        """Cubre existe/existen/existir/existía/existiendo + prefijo."""
        for frase in (
            "no existe contrato pactado",
            "al no existir contrato pactado",
            "de no existir contrato pactado",
            "no existía contrato pactado",
            "no existen contrato",
        ):
            d = f"El servicio se facturó porque {frase} con la entidad."
            out = _reescribir_negacion_contrato(d, texto_glosa=_GLOSA_MEDIMAS)
            assert "CTR-2024-MEDIMAS-HUS" in out, f"no reescribió: {frase!r}"

    def test_no_sobrecaptura_afirmaciones(self):
        """Frases AFIRMATIVAS sobre el contrato NO deben tocarse."""
        afirm = (
            "El contrato pactado define la tarifa; existe contrato pactado "
            "vigente entre las partes, según el contrato CTR-2024-MEDIMAS-HUS."
        )
        out = _reescribir_negacion_contrato(afirm, texto_glosa=_GLOSA_MEDIMAS)
        assert out == afirm

    def test_glosa_sin_contrato_no_toca_nada(self):
        """Si la glosa NO cita contrato (aseguradora SOAT pura), el cuerpo
        queda intacto aunque diga 'no existir contrato pactado'."""
        d = "Se facturó SOAT pleno al no existir contrato pactado con la aseguradora."
        out = _reescribir_negacion_contrato(d, texto_glosa="SOAT puro, sin contrato citado")
        assert out == d

    def test_sin_contrato_pactado_clasico_sigue_funcionando(self):
        """Regresión: la variante original 'SIN CONTRATO PACTADO' no se rompe."""
        d = "Contrato: SIN CONTRATO PACTADO. El servicio fue prestado."
        out = _reescribir_negacion_contrato(d, texto_glosa=_GLOSA_MEDIMAS)
        assert "SIN CONTRATO PACTADO" not in out
        assert "CTR-2024-MEDIMAS-HUS" in out


# ── Bug #2: hint SOAT-pleno no debe inyectarse si la glosa cita contrato ──


def _capturar_system_prompt(monkeypatch):
    """Stub de _llamar_ia que captura el system prompt enviado a la IA."""
    from app.services.glosa_service import GlosaService

    capturado = {}

    async def fake(self, system, user, *a, **k):
        capturado["system"] = system
        return (
            "<paciente>X</paciente><argumento>LA ESE HUS NO ACEPTA LA GLOSA. "
            "LOS SERVICIOS FUERON PRESTADOS Y SOPORTADOS. SE SOLICITA EL "
            "LEVANTAMIENTO Y EL PAGO INTEGRO.</argumento>",
            "stub-test",
        )

    monkeypatch.setattr(GlosaService, "_llamar_ia", fake)
    return capturado


def _prep_min(monkeypatch):
    monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
    monkeypatch.delenv("TOOL_USE_HABILITADO", raising=False)
    monkeypatch.delenv("MULTI_AGENT_HABILITADO", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import app.services.dictamen_directo as dd
    import app.services.validador_dictamen as vd

    monkeypatch.setattr(vd, "detectar_defectos_criticos", lambda *a, **k: [])
    monkeypatch.setattr(dd, "puede_emitir_directo", lambda *a, **k: False)


def _svc():
    from app.services.glosa_service import GlosaService

    return GlosaService(groq_api_key=None, anthropic_api_key=None, primary_ai="groq")


def _data(texto, eps="OTRA / SIN DEFINIR"):
    from app.models.schemas import GlosaInput

    return GlosaInput(eps=eps, etapa="RESPUESTA A GLOSA", tabla_excel=texto, valor_aceptado="0")


class TestBug2SoatConContrato:
    @pytest.mark.asyncio
    async def test_glosa_con_contrato_no_inyecta_hint_sin_contrato(self, monkeypatch):
        """Glosa que cita CTR + SOAT × 0.85 → NO debe pedir 'SOAT pleno / sin
        contrato'; debe pedir defensa intra-contrato."""
        _prep_min(monkeypatch)
        cap = _capturar_system_prompt(monkeypatch)
        glosa = (
            "TARIFA: el contrato vigente CTR-2024-MEDIMAS-HUS define para "
            "prostatectomía una tarifa de SOAT × 0.85; la facturación aplicó "
            "SOAT pleno + adicional 35%."
        )
        await _svc().analizar(_data(glosa))
        sysp = cap["system"]
        assert "NO HAY CONTRATO PACTADO, por lo que rige" not in sysp
        assert "TARIFA CON CONTRATO PACTADO" in sysp
        assert "CTR-2024-MEDIMAS-HUS" in sysp

    @pytest.mark.asyncio
    async def test_glosa_soat_puro_si_inyecta_hint_sin_contrato(self, monkeypatch):
        """Aseguradora SOAT pura (sin contrato citado) → SÍ mantiene el hint
        clásico de 'sin contrato → SOAT pleno' (no romper el caso legítimo)."""
        _prep_min(monkeypatch)
        cap = _capturar_system_prompt(monkeypatch)
        glosa = (
            "U220154 - COMPAÑIA MUNDIAL DE SEGUROS S.A. SOAT UVB. Diferencia "
            "tarifaria en atención inicial de urgencias por accidente de tránsito."
        )
        await _svc().analizar(_data(glosa))
        sysp = cap["system"]
        assert "ASEGURADORA SOAT" in sysp
        assert "TARIFA CON CONTRATO PACTADO" not in sysp


# ── Bug #9: vocabulario de cobertura (evento adverso / liquidación) ──


class TestBug9VocabularioCobertura:
    def test_evento_adverso_se_detecta_como_clave(self):
        """Un sub-concepto de evento adverso ahora tiene 'claves' → puede
        marcarse como omitido si el dictamen no lo aborda."""
        from app.services.subconceptos_glosa import (
            auditar_subconceptos_respondidos,
            detectar_subconceptos,
        )

        glosa = (
            "Se objeta: (1) la fístula urinaria es un EVENTO ADVERSO PREVENIBLE "
            "atribuible a falla en la técnica quirúrgica; (2) la TARIFA aplicada "
            "excede lo pactado."
        )
        subs = detectar_subconceptos(glosa)
        assert len(subs) >= 2
        # Dictamen que solo habla de tarifa, NO del evento adverso
        dictamen = "Sobre la tarifa, se aplicó el manual vigente conforme a lo pactado."
        ok, omitidos = auditar_subconceptos_respondidos(dictamen, subs)
        assert not ok
        assert any("evento adverso" in o.lower() or "fístula" in o.lower() for o in omitidos)

    def test_liquidacion_se_detecta_como_clave(self):
        from app.services.subconceptos_glosa import (
            auditar_subconceptos_respondidos,
            detectar_subconceptos,
        )

        glosa = (
            "(1) PERTINENCIA: el procedimiento no se justifica. (2) Dado el "
            "proceso de LIQUIDACIÓN de la EPS, el reconocimiento queda "
            "condicionado a la verificación de saldos por la AGENTE LIQUIDADORA."
        )
        subs = detectar_subconceptos(glosa)
        dictamen = "Sobre la pertinencia, la decisión corresponde al médico tratante."
        ok, omitidos = auditar_subconceptos_respondidos(dictamen, subs)
        assert not ok
        assert any("liquidaci" in o.lower() or "saldos" in o.lower() for o in omitidos)
