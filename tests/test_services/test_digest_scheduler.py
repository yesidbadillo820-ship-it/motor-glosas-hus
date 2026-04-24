"""Tests del scheduler del digest (Ronda 20)."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.services import digest_scheduler as ds


# ─── _config ───────────────────────────────────────────────────────────────

class TestConfig:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("DIGEST_HORA", raising=False)
        monkeypatch.delenv("DIGEST_MINUTO", raising=False)
        monkeypatch.delenv("DIGEST_CANAL", raising=False)
        monkeypatch.delenv("DIGEST_DESTINATARIOS", raising=False)
        monkeypatch.delenv("DIGEST_PERIODO", raising=False)
        c = ds._config()
        assert c["hora"] == 7
        assert c["minuto"] == 30
        assert c["canal"] == "mock"
        assert c["destinatarios"] == []
        assert c["periodo"] == "dia"

    def test_lee_env(self, monkeypatch):
        monkeypatch.setenv("DIGEST_HORA", "8")
        monkeypatch.setenv("DIGEST_MINUTO", "0")
        monkeypatch.setenv("DIGEST_CANAL", "whatsapp")
        monkeypatch.setenv("DIGEST_DESTINATARIOS", "+573001,+573002")
        monkeypatch.setenv("DIGEST_PERIODO", "semana")
        c = ds._config()
        assert c["hora"] == 8
        assert c["canal"] == "whatsapp"
        assert c["destinatarios"] == ["+573001", "+573002"]
        assert c["periodo"] == "semana"

    def test_destinatarios_trim_y_skip_vacios(self, monkeypatch):
        monkeypatch.setenv("DIGEST_DESTINATARIOS", "  +573001 , , +573002  ")
        c = ds._config()
        assert c["destinatarios"] == ["+573001", "+573002"]


# ─── _segundos_hasta_proximo_envio ─────────────────────────────────────────

class TestProximoEnvio:
    def test_retorna_valor_positivo_menor_24h(self):
        s = ds._segundos_hasta_proximo_envio()
        assert 0 < s <= 86400


# ─── obtener_estado ────────────────────────────────────────────────────────

class TestEstado:
    def test_estructura_inicial(self):
        e = ds.obtener_estado()
        assert "scheduler_activo" in e
        assert "ejecucion_en_curso" in e
        assert "ultima_ejecucion" in e
        assert "config" in e
        assert "hora" in e["config"]


# ─── ejecutar_envio_digest ─────────────────────────────────────────────────

class TestEjecutarEnvio:
    @pytest.mark.asyncio
    async def test_sin_destinatarios_retorna_skip(self, monkeypatch):
        monkeypatch.setenv("DIGEST_DESTINATARIOS", "")
        ds._EJECUCION_EN_CURSO = False
        r = await ds.ejecutar_envio_digest()
        assert "skip" in r

    @pytest.mark.asyncio
    async def test_ejecucion_concurrente_se_bloquea(self):
        ds._EJECUCION_EN_CURSO = True
        try:
            r = await ds.ejecutar_envio_digest()
            assert "skip" in r
        finally:
            ds._EJECUCION_EN_CURSO = False

    @pytest.mark.asyncio
    async def test_envia_a_todos_los_destinatarios(self, monkeypatch):
        monkeypatch.setenv("DIGEST_DESTINATARIOS", "+573001,+573002,+573003")
        monkeypatch.setenv("DIGEST_CANAL", "mock")
        ds._EJECUCION_EN_CURSO = False

        fake_db = MagicMock()
        fake_digest = {
            "periodo": "dia", "estado_general": "OK", "desde": "", "hasta": "",
            "indicadores": {"radicadas": 0, "respondidas": 0, "valor_objetado": 0,
                            "valor_recuperado": 0, "tasa_recuperacion": 0},
            "operativo": {"pendientes_total": 0, "vencidas": 0},
            "autopilot": {"LISTA_ENVIAR": 0, "CASI_LISTA": 0, "REVISAR": 0, "INTERVENIR": 0},
            "top_eps": [], "alertas": [],
        }
        with patch("app.services.digest_scheduler.SessionLocal", return_value=fake_db), \
             patch("app.services.digest_scheduler.generar_digest", return_value=fake_digest):
            r = await ds.ejecutar_envio_digest()
        assert r["procesados"] == 3
        assert r["enviados_ok"] == 3  # mock siempre OK
        assert r["canal"] == "mock"


# ─── iniciar/detener scheduler ─────────────────────────────────────────────

class TestSchedulerControl:
    def test_no_inicia_sin_destinatarios(self, monkeypatch):
        monkeypatch.setenv("DIGEST_DESTINATARIOS", "")
        ds._SCHEDULER_TASK = None
        ds.iniciar_scheduler()
        assert ds._SCHEDULER_TASK is None

    def test_detener_sin_task_es_idempotente(self):
        ds._SCHEDULER_TASK = None
        ds.detener_scheduler()
        assert ds._SCHEDULER_TASK is None
