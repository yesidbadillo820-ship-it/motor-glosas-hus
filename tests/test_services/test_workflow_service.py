"""Tests de WorkflowService (Ronda 50 Paso 6)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.workflow_service import (
    EstadoGlosa,
    TRANSICIONES_PERMITIDAS,
    WorkflowService,
)


class TestTransicionesPermitidas:
    def test_radicada_a_respondida_valida(self):
        assert WorkflowService.puede_transicionar("RADICADA", "RESPONDIDA") is True

    def test_respondida_a_ratificada(self):
        assert WorkflowService.puede_transicionar("RESPONDIDA", "RATIFICADA") is True

    def test_respondida_a_levantada(self):
        assert WorkflowService.puede_transicionar("RESPONDIDA", "LEVANTADA") is True

    def test_ratificada_a_conciliada(self):
        assert WorkflowService.puede_transicionar("RATIFICADA", "CONCILIADA") is True

    def test_ratificada_a_escalada_sns(self):
        assert WorkflowService.puede_transicionar("RATIFICADA", "ESCALADA_SNS") is True

    def test_extemporanea_a_respondida(self):
        """Glosa importada como EXTEMPORANEA sí puede marcarse respondida."""
        assert WorkflowService.puede_transicionar("EXTEMPORANEA", "RESPONDIDA") is True

    def test_ratificada_a_respondida_permitido(self):
        """Auto-aplicación de texto fijo Ronda 21: una glosa RATIFICADA
        puede moverse a RESPONDIDA cuando el autopilot aplica texto fijo."""
        assert WorkflowService.puede_transicionar("RATIFICADA", "RESPONDIDA") is True


class TestTransicionesInvalidas:
    def test_radicada_a_conciliada_no_permitida_directo(self):
        assert WorkflowService.puede_transicionar("RADICADA", "CONCILIADA") is False

    def test_radicada_a_ratificada_no_permitida(self):
        """Hay que pasar por RESPONDIDA antes."""
        assert WorkflowService.puede_transicionar("RADICADA", "RATIFICADA") is False

    def test_levantada_a_otro_no_permitido(self):
        """LEVANTADA es estado terminal."""
        assert WorkflowService.puede_transicionar("LEVANTADA", "RESPONDIDA") is False

    def test_respondida_a_respondida_no_permitido(self):
        """Idempotencia: no se puede transicionar al mismo estado."""
        # Esto es lo que causó el bug que arreglamos en Ronda 41
        assert WorkflowService.puede_transicionar("RESPONDIDA", "RESPONDIDA") is False

    def test_estados_inexistentes(self):
        assert WorkflowService.puede_transicionar("INVENTADO", "RESPONDIDA") is False
        assert WorkflowService.puede_transicionar("RESPONDIDA", "INVENTADO") is False


class TestObtenerTransicionesValidas:
    def test_desde_radicada(self):
        trans = WorkflowService.obtener_transiciones_validas("RADICADA")
        destinos = [t.hacia for t in trans]
        assert "RESPONDIDA" in destinos

    def test_desde_respondida(self):
        trans = WorkflowService.obtener_transiciones_validas("RESPONDIDA")
        destinos = [t.hacia for t in trans]
        assert "RATIFICADA" in destinos
        assert "LEVANTADA" in destinos
        assert "CONCILIADA" in destinos

    def test_desde_terminal_vacio(self):
        """LEVANTADA es terminal — no hay transiciones desde ahí."""
        trans = WorkflowService.obtener_transiciones_validas("LEVANTADA")
        assert trans == []


class TestEnumEstados:
    def test_estados_son_strings_validos(self):
        assert EstadoGlosa.RADICADA.value == "RADICADA"
        assert EstadoGlosa.RESPONDIDA.value == "RESPONDIDA"
        assert EstadoGlosa.LEVANTADA.value == "LEVANTADA"

    def test_cantidad_estados_esperada(self):
        # 8 estados canónicos definidos
        assert len(EstadoGlosa) == 8


class TestIntegridadTransiciones:
    def test_todas_tienen_desde_hacia_accion(self):
        """Sanity check de la tabla: ningún TransicionWorkflow mal formado."""
        for t in TRANSICIONES_PERMITIDAS:
            assert t.desde
            assert t.hacia
            assert t.accion
            assert t.desde != t.hacia  # nunca circular
