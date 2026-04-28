"""Tests para app.services.memoria_gestor."""
from __future__ import annotations

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")  # noqa: F841

from app.services.memoria_gestor import (  # noqa: E402
    _clasificar_mensaje,
    _hint_de_etiqueta,
)


class TestClasificarMensaje:
    def test_T760(self):
        et = _clasificar_mensaje("Agrega cita a la Sentencia T-760/2008 por favor")
        assert "T-760" in et

    def test_articulo_177(self):
        et = _clasificar_mensaje("incluye Art. 177 Ley 100")
        assert "Art. 177" in et

    def test_tono_conciliador(self):
        et = _clasificar_mensaje("baja el tono, hazlo más conciliador")
        assert "tono conciliador" in et

    def test_tono_firme(self):
        et = _clasificar_mensaje("súbele el tono, más firme")
        assert "tono firme" in et

    def test_acortar(self):
        et = _clasificar_mensaje("Acórtalo, está muy largo")
        assert "corto" in et

    def test_supersalud(self):
        et = _clasificar_mensaje("menciona escalamiento a SuperSalud")
        assert "SuperSalud" in et

    def test_circular_047(self):
        et = _clasificar_mensaje("agrega cita a la Circular 047 de 2025")
        assert "Circular 047" in et

    def test_mensaje_vacio(self):
        assert _clasificar_mensaje("") == []
        assert _clasificar_mensaje(None) == []

    def test_combinacion(self):
        et = _clasificar_mensaje("Agrega T-760 y baja el tono a conciliador")
        assert "T-760" in et
        assert "tono conciliador" in et


class TestHintDeEtiqueta:
    def test_T760_tiene_hint(self):
        h = _hint_de_etiqueta("T-760")
        assert "T-760" in h or "PBS" in h

    def test_etiqueta_inexistente(self):
        assert _hint_de_etiqueta("NO_EXISTE") == ""
