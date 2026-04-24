"""Tests del detector central de texto fijo (Ronda 21).

Verifica la regla dura: RATIFICADA SIEMPRE gana sobre EXTEMPORÁNEA.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.texto_fijo_detector import (
    DIAS_HABILES_LIMITE,
    _es_extemporanea,
    _es_ratificada,
    _no_aplicar_extemporaneidad,
    aplicar_texto_fijo_si_corresponde,
    clasificar_texto_fijo,
)


def _mock_glosa(**kw):
    """Objeto duck-typed con los atributos que el detector consulta."""
    defaults = dict(
        eps="FAMISANAR EPS",
        factura="F-1",
        estado="PENDIENTE",
        workflow_state="RADICADA",
        radicado_info="",
        referencia="",
        nota_workflow="",
        tipo_glosa_excel="",
        observacion_tecnico="",
        dias_radicacion_dgh=0,
        fecha_radicacion_factura=None,
        fecha_documento_dgh=None,
        dictamen="",
        modelo_ia="",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


# ─── _es_ratificada ────────────────────────────────────────────────────────

class TestEsRatificada:
    def test_estado_ratificada(self):
        g = _mock_glosa(estado="RATIFICADA")
        assert _es_ratificada(g) is True

    def test_workflow_state_ratificada(self):
        g = _mock_glosa(workflow_state="RATIFICADA")
        assert _es_ratificada(g) is True

    def test_radicado_info_contiene_ratificada(self):
        g = _mock_glosa(radicado_info="OBSERVACIÓN: GLOSA RATIFICADA POR LA EPS")
        assert _es_ratificada(g) is True

    def test_referencia_contiene_ratificada(self):
        g = _mock_glosa(referencia="2da ronda - Ratificada con sustento")
        assert _es_ratificada(g) is True

    def test_sin_ratif_retorna_false(self):
        g = _mock_glosa(estado="PENDIENTE", radicado_info="glosa inicial")
        assert _es_ratificada(g) is False


# ─── _no_aplicar_extemporaneidad ───────────────────────────────────────────

class TestNoAplicarExtemporaneidad:
    def test_flag_explicito(self):
        g = _mock_glosa(observacion_tecnico="NO APLICAR EXTEMPORANEIDAD - FOMAG")
        assert _no_aplicar_extemporaneidad(g) is True

    def test_sin_flag(self):
        g = _mock_glosa(observacion_tecnico="revisar tarifa")
        assert _no_aplicar_extemporaneidad(g) is False


# ─── _es_extemporanea ──────────────────────────────────────────────────────

class TestEsExtemporanea:
    def test_por_campo_precalculado(self):
        g = _mock_glosa(dias_radicacion_dgh=25)
        es, d = _es_extemporanea(g)
        assert es is True
        assert d == 25

    def test_justo_en_limite_no_es_extemporanea(self):
        g = _mock_glosa(dias_radicacion_dgh=20)
        es, d = _es_extemporanea(g)
        assert es is False

    def test_flag_salta_extemporaneidad(self):
        g = _mock_glosa(
            dias_radicacion_dgh=30,
            observacion_tecnico="NO APLICAR EXTEMPORANEIDAD",
        )
        es, _ = _es_extemporanea(g)
        assert es is False

    def test_sin_datos_no_es_extemporanea(self):
        g = _mock_glosa()
        es, d = _es_extemporanea(g)
        assert es is False
        assert d == 0

    def test_calcula_desde_fechas_si_no_hay_precalculado(self):
        ahora = datetime.now(timezone.utc)
        g = _mock_glosa(
            dias_radicacion_dgh=None,
            fecha_radicacion_factura=ahora - timedelta(days=45),
            fecha_documento_dgh=ahora,
        )
        es, d = _es_extemporanea(g)
        # 45 días calendario con ~32 días hábiles > 20 → extemporánea
        assert es is True


# ─── clasificar_texto_fijo — regla de prioridad ────────────────────────────

class TestPrioridad:
    def test_ratificada_sola(self):
        g = _mock_glosa(estado="RATIFICADA")
        r = clasificar_texto_fijo(g)
        assert r is not None
        assert r["tipo"] == "RATIFICADA"
        assert "RATIFICADA" in r["dictamen_html"].upper()

    def test_extemporanea_sola(self):
        g = _mock_glosa(dias_radicacion_dgh=25)
        r = clasificar_texto_fijo(g)
        assert r is not None
        assert r["tipo"] == "EXTEMPORANEA"
        assert r["dias_extemporaneidad"] == 25

    def test_ratificada_gana_sobre_extemporanea(self):
        """EL TEST CLAVE: si ambas aplican, RATIFICADA gana y el dictamen
        NO menciona extemporaneidad."""
        g = _mock_glosa(
            estado="RATIFICADA",
            dias_radicacion_dgh=30,   # también extemporánea
        )
        r = clasificar_texto_fijo(g)
        assert r is not None
        assert r["tipo"] == "RATIFICADA"
        # El dictamen NO debe mencionar la palabra EXTEMPORÁNEA
        html_upper = r["dictamen_html"].upper()
        assert "EXTEMPORÁNEA" not in html_upper
        assert "EXTEMPORANEA" not in html_upper

    def test_ratificada_por_radicado_info_gana(self):
        g = _mock_glosa(
            estado="PENDIENTE",
            radicado_info="GLOSA RATIFICADA POR LA EPS",
            dias_radicacion_dgh=35,   # también extemporánea
        )
        r = clasificar_texto_fijo(g)
        assert r["tipo"] == "RATIFICADA"

    def test_ninguna_aplica(self):
        g = _mock_glosa(dias_radicacion_dgh=5)
        assert clasificar_texto_fijo(g) is None

    def test_none_safe(self):
        assert clasificar_texto_fijo(None) is None


# ─── aplicar_texto_fijo_si_corresponde ─────────────────────────────────────

class TestAplicar:
    def test_aplica_y_muta(self):
        g = _mock_glosa(estado="RATIFICADA")
        r = aplicar_texto_fijo_si_corresponde(g)
        assert r is not None
        assert "RATIFICADA" in g.dictamen.upper()
        assert "texto_fijo" in g.modelo_ia
        assert "RATIFICADA" in g.modelo_ia

    def test_marca_workflow_respondida_automaticamente(self):
        """Hotfix Ronda 34: al aplicar texto fijo, workflow_state debe pasar
        a RESPONDIDA para que la glosa salga de la bandeja de pendientes."""
        g = _mock_glosa(estado="PENDIENTE", workflow_state="RATIFICADA")
        r = aplicar_texto_fijo_si_corresponde(g)
        assert r is not None
        assert g.workflow_state == "RESPONDIDA"
        assert g.fecha_decision_eps is not None
        assert "automáticamente" in (g.nota_workflow or "").lower()

    def test_extemporanea_tambien_queda_respondida(self):
        g = _mock_glosa(dias_radicacion_dgh=30, workflow_state="BORRADOR")
        r = aplicar_texto_fijo_si_corresponde(g)
        assert r is not None
        assert r["tipo"] == "EXTEMPORANEA"
        assert g.workflow_state == "RESPONDIDA"

    def test_no_revierte_workflow_ya_terminal(self):
        g = _mock_glosa(estado="RATIFICADA", workflow_state="CONCILIADA")
        aplicar_texto_fijo_si_corresponde(g)
        assert g.workflow_state == "CONCILIADA"  # no se reescribe

    def test_no_sobreescribe_dictamen_IA_existente(self):
        g = _mock_glosa(
            estado="PENDIENTE",
            dias_radicacion_dgh=25,
            dictamen="<p>Dictamen generado por IA de 2000 caracteres…</p>",
            modelo_ia="anthropic/claude-sonnet",
        )
        r = aplicar_texto_fijo_si_corresponde(g)
        # No lo aplica porque hay dictamen IA válido
        assert r is None
        assert "Dictamen generado por IA" in g.dictamen

    def test_idempotente_mismo_tipo(self):
        g = _mock_glosa(
            estado="RATIFICADA",
            dictamen="<p>ya existente</p>",
            modelo_ia="pre-analisis/texto_fijo/RATIFICADA",
        )
        # Segundo llamado no reescribe
        r = aplicar_texto_fijo_si_corresponde(g)
        assert r is None
        assert g.dictamen == "<p>ya existente</p>"

    def test_cambio_de_tipo_reescribe(self):
        """Si antes era EXTEMPORANEA pero ahora es RATIFICADA, debe reescribir."""
        g = _mock_glosa(
            estado="RATIFICADA",
            dias_radicacion_dgh=30,
            dictamen="<p>dictamen extemporánea viejo</p>",
            modelo_ia="pre-analisis/texto_fijo/EXTEMPORANEA",
        )
        r = aplicar_texto_fijo_si_corresponde(g)
        assert r is not None
        assert r["tipo"] == "RATIFICADA"
        assert "RATIFICADA" in g.modelo_ia.upper()


# ─── DIAS_HABILES_LIMITE ───────────────────────────────────────────────────

def test_limite_legal_es_20():
    """Constante alineada con Art. 56/57 Ley 1438/2011."""
    assert DIAS_HABILES_LIMITE == 20
