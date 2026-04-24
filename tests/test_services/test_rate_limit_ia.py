"""Tests del rate limiter unificado IA (Ronda 50 Paso 3)."""
from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.services import rate_limit_ia as rl


@pytest.fixture(autouse=True)
def _reset_state():
    """Cada test arranca con registro vacío."""
    rl._REGISTRO.clear()
    yield
    rl._REGISTRO.clear()


def _request_mock(host: str = "127.0.0.1"):
    r = MagicMock()
    r.client = SimpleNamespace(host=host)
    return r


def _user(email: str = "gestor@hus.com"):
    return SimpleNamespace(email=email)


class TestLimiteBasico:
    def test_primera_llamada_pasa(self):
        rl.consumir_cupo_ia(_request_mock(), _user())

    def test_debajo_del_limite_pasa(self):
        u = _user()
        req = _request_mock()
        for _ in range(rl.LIMITE_MINUTO_USUARIO - 1):
            rl.consumir_cupo_ia(req, u)

    def test_exceder_minuto_devuelve_429(self):
        u = _user()
        req = _request_mock()
        for _ in range(rl.LIMITE_MINUTO_USUARIO):
            rl.consumir_cupo_ia(req, u)
        with pytest.raises(HTTPException) as exc:
            rl.consumir_cupo_ia(req, u)
        assert exc.value.status_code == 429
        assert "Retry-After" in exc.value.headers


class TestAisladoEntreUsuarios:
    def test_un_usuario_no_bloquea_a_otro(self):
        req = _request_mock()
        for _ in range(rl.LIMITE_MINUTO_USUARIO):
            rl.consumir_cupo_ia(req, _user("a@hus.com"))
        # B con su cuota limpia
        rl.consumir_cupo_ia(req, _user("b@hus.com"))


class TestLimiteIP:
    def test_ip_anonima_bloquea_en_limite_minuto(self):
        """Sin usuario autenticado, el límite efectivo es
        min(LIMITE_MINUTO_USUARIO, LIMITE_MINUTO_IP) — el que llegue antes."""
        usuario_anon = SimpleNamespace(email="")
        req = _request_mock(host="10.0.0.1")
        limite_efectivo = min(rl.LIMITE_MINUTO_USUARIO, rl.LIMITE_MINUTO_IP)
        for _ in range(limite_efectivo):
            rl.consumir_cupo_ia(req, usuario_anon)
        with pytest.raises(HTTPException):
            rl.consumir_cupo_ia(req, usuario_anon)


class TestEstadoCupo:
    def test_reporta_uso_actual(self):
        u = _user()
        req = _request_mock()
        for _ in range(3):
            rl.consumir_cupo_ia(req, u)
        estado = rl.estado_cupo(u)
        assert estado["en_minuto"] == 3
        assert estado["limite_minuto"] == rl.LIMITE_MINUTO_USUARIO

    def test_estado_sin_llamadas(self):
        estado = rl.estado_cupo(_user("nuevo@hus.com"))
        # defaultdict crea vacío al consultar — no explotar
        assert estado["en_minuto"] == 0
