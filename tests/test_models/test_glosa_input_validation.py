"""Tests de validación de GlosaInput (R55 P1)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.schemas import GlosaInput


def _input_minimo(**kw):
    base = dict(eps="FAMISANAR", etapa="RESPUESTA", tabla_excel="aaa bbb ccc")
    base.update(kw)
    return GlosaInput(**base)


class TestTonoValidator:
    def test_tono_valido_conciliador(self):
        assert _input_minimo(tono="conciliador").tono == "conciliador"

    def test_tono_valido_firme(self):
        assert _input_minimo(tono="firme").tono == "firme"

    def test_tono_valido_neutral(self):
        assert _input_minimo(tono="neutral").tono == "neutral"

    def test_tono_invalido_fallback_default(self):
        """Hardening: input desconocido NO rompe el request, fallback a default."""
        assert _input_minimo(tono="hacker").tono == "conciliador"

    def test_tono_case_insensitive(self):
        assert _input_minimo(tono="FIRME").tono == "firme"
        assert _input_minimo(tono="  Conciliador  ").tono == "conciliador"

    def test_tono_vacio_o_none(self):
        assert _input_minimo(tono=None).tono == "conciliador"
        assert _input_minimo(tono="").tono == "conciliador"


class TestModoRespuestaValidator:
    def test_modos_validos(self):
        assert _input_minimo(modo_respuesta="defender").modo_respuesta == "defender"
        assert _input_minimo(modo_respuesta="aceptar_total").modo_respuesta == "aceptar_total"
        assert _input_minimo(modo_respuesta="aceptar_parcial").modo_respuesta == "aceptar_parcial"

    def test_modo_auditoria_previa_valido(self):
        """R59 P1: nuevo modo de auditoría neutral sin redactar dictamen."""
        assert _input_minimo(modo_respuesta="auditoria_previa").modo_respuesta == "auditoria_previa"

    def test_modo_auditoria_previa_case_insensitive(self):
        assert _input_minimo(modo_respuesta="AUDITORIA_PREVIA").modo_respuesta == "auditoria_previa"
        assert _input_minimo(modo_respuesta="  Auditoria_Previa  ").modo_respuesta == "auditoria_previa"

    def test_modo_invalido_fallback_defender(self):
        assert _input_minimo(modo_respuesta="rebelde").modo_respuesta == "defender"


class TestPayloadLimit:
    def test_tabla_excel_max_50000_chars(self):
        """Hardening anti-DoS: tabla_excel limitada a 50KB."""
        with pytest.raises(ValidationError) as exc:
            _input_minimo(tabla_excel="x" * 60_000)
        assert "tabla_excel" in str(exc.value).lower() or "50000" in str(exc.value)

    def test_tabla_excel_50000_aceptado(self):
        """Justo en el límite debe aceptarse."""
        assert _input_minimo(tabla_excel="x" * 50_000).tabla_excel
