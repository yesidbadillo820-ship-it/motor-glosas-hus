"""Tests del endpoint /sistema/observabilidad (Ronda 50 Paso 12)."""
from __future__ import annotations

from unittest.mock import MagicMock


def test_observabilidad_estructura(monkeypatch):
    from app.api.routers.sistema import observabilidad
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("FIRMA_DIGITAL_PRIVATE_KEY", raising=False)
    user = MagicMock(email="admin@hus.com", rol="SUPER_ADMIN")
    r = observabilidad(current_user=user)
    assert "version" in r
    assert "configuracion" in r
    assert "schedulers" in r
    assert "metricas_codigo" in r
    assert "recomendaciones" in r


def test_observabilidad_recomendaciones_sin_config(monkeypatch):
    """Si nada está configurado, hay recomendaciones para todo."""
    from app.api.routers.sistema import observabilidad
    for k in ("SENTRY_DSN", "ANTHROPIC_API_KEY", "GROQ_API_KEY",
              "FIRMA_DIGITAL_PRIVATE_KEY", "GLOSAS_ENCRYPTION_KEY",
              "DIGEST_DESTINATARIOS", "WHATSAPP_META_TOKEN", "TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    user = MagicMock(email="admin@hus.com", rol="SUPER_ADMIN")
    r = observabilidad(current_user=user)
    # Debe haber al menos 5 recomendaciones (sentry, IA, firma, cifrado, digest, bots)
    assert len(r["recomendaciones"]) >= 5
    # CRÍTICO de IA debe aparecer
    assert any("CRÍTICO" in rec for rec in r["recomendaciones"])


def test_observabilidad_con_anthropic(monkeypatch):
    from app.api.routers.sistema import observabilidad
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
    user = MagicMock(email="admin@hus.com", rol="SUPER_ADMIN")
    r = observabilidad(current_user=user)
    assert r["configuracion"]["anthropic"] is True
    # Si Anthropic está y Groq también puede o no, no hay "CRÍTICO IA"
    assert not any("CRÍTICO" in rec and "IA" in rec for rec in r["recomendaciones"])


def test_metricas_codigo_presentes():
    from app.api.routers.sistema import observabilidad
    user = MagicMock(email="admin@hus.com", rol="SUPER_ADMIN")
    r = observabilidad(current_user=user)
    m = r["metricas_codigo"]
    assert m["rondas_desplegadas"] >= 50
    assert m["tests_total"] >= 500
    assert m["endpoints"] > 100
