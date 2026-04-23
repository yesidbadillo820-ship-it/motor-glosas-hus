"""Tests del bot de mensajería (Ronda 13)."""
from app.services.bot_mensajeria import (
    MockProvider,
    WhatsAppMetaProvider,
    TelegramProvider,
    enviar_notificacion,
    get_provider,
    plantilla_asignacion,
    plantilla_coordinador_diario,
    plantilla_decision_levantada,
    plantilla_glosa_vencida,
)


def test_mock_provider_siempre_ok():
    p = MockProvider()
    r = p.enviar("+573001234567", "Hola mundo")
    assert r["ok"] is True
    assert r["provider"] == "mock"
    assert "delivered_at" in r


def test_whatsapp_sin_token_cae_a_mock():
    # Sin env vars configuradas, disponible() retorna False
    p = WhatsAppMetaProvider()
    assert not p.disponible()
    r = p.enviar("+573001234567", "Hola")
    # Se degrada a mock
    assert r["ok"] is True
    assert r["provider"] == "mock"


def test_telegram_sin_token_cae_a_mock():
    p = TelegramProvider()
    assert not p.disponible()
    r = p.enviar("1234", "Hola")
    assert r["ok"] is True
    assert r["provider"] == "mock"


def test_get_provider_alias():
    assert get_provider("whatsapp").__class__.__name__ in ("WhatsAppMetaProvider", "MockProvider")
    assert get_provider("telegram").__class__.__name__ in ("TelegramProvider", "MockProvider")
    assert get_provider("mock").__class__.__name__ == "MockProvider"
    assert get_provider("inexistente").__class__.__name__ == "MockProvider"


def test_enviar_notificacion_api_pubica():
    r = enviar_notificacion("+573001234567", "Test", canal="mock")
    assert r["ok"] is True


def test_plantilla_vencida_contiene_datos():
    m = plantilla_glosa_vencida(42, "TA0201", "FAMISANAR EPS", 50000, 2)
    assert "42" in m
    assert "TA0201" in m
    assert "FAMISANAR" in m
    assert "50,000" in m
    assert "2d" in m or "2 d" in m


def test_plantilla_asignacion_menciona_auditor():
    m = plantilla_asignacion(10, "SO0101", "JUAN PEREZ")
    assert "JUAN PEREZ" in m
    assert "10" in m
    assert "SO0101" in m


def test_plantilla_levantada_incluye_recuperado():
    m = plantilla_decision_levantada(7, "FA0801", 200_000)
    assert "7" in m
    assert "200,000" in m
    assert "Gold" in m


def test_plantilla_coordinador_incluye_metricas():
    m = plantilla_coordinador_diario(vencidas=3, criticas_48h=5, recuperado_mes=1_500_000)
    assert "3" in m
    assert "5" in m
    assert "1,500,000" in m
