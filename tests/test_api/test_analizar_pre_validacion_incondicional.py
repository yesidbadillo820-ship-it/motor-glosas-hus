"""Tests: pre-validación de texto de glosa CORRE AUNQUE el Quality Gate
esté OFF.

Regresión del bug visible en producción 10-jun-2026: el gestor pegó
"Se glosa por falta de cobertura" (33 chars), el QG estaba OFF, así que
el wrapper QG nunca corría → el input basura llegaba al IA y se generaba
un dictamen con valores y contratos inventados.

Ahora `analizar()` corre check_texto_glosa INCONDICIONALMENTE antes de
gastar un call de IA. Bloquea con HTTP 400 + mensaje legible.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import UsuarioRecord


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def usuario():
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _form(eps="DISPENSARIO MEDICO", texto="Se glosa por falta de cobertura"):
    return {
        "eps": eps,
        "etapa": "INICIAL",
        "valor_aceptado": "0",
        "tabla_excel": texto,
        "tono": "conciliador",
        "modo_respuesta": "defender",
    }


class TestPreValidacionIncondicional:
    def test_input_corto_bloqueado_con_flag_off(self, client, monkeypatch):
        """Aunque QUALITY_GATE_ENABLED esté OFF, el input corto se bloquea
        antes de gastar un call de IA."""
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)

        # Espía sobre _llamar_ia para asegurar que NUNCA se llama
        with patch("app.services.glosa_service.GlosaService._llamar_ia") as spy_llamar_ia:
            r = client.post("/analizar", data=_form(texto="Se glosa por falta de cobertura"))
            assert r.status_code == 400, r.text
            detail = r.json().get("detail", "")
            assert "corto" in detail.lower() or "mínimo" in detail.lower()
            spy_llamar_ia.assert_not_called()  # IA NUNCA se llamó

    def test_input_corto_bloqueado_con_flag_on(self, client, monkeypatch):
        """Con QG ON el mismo input se bloquea por el mismo check
        (idempotente, no genera 2 errores)."""
        monkeypatch.setenv("QUALITY_GATE_ENABLED", "1")
        monkeypatch.setenv("QUALITY_GATE_ROLLOUT_PCT", "100")
        with patch("app.services.glosa_service.GlosaService._llamar_ia") as spy_llamar_ia:
            r = client.post("/analizar", data=_form(texto="Se glosa por falta de cobertura"))
            assert r.status_code == 400
            spy_llamar_ia.assert_not_called()

    def test_input_sin_dominio_bloqueado(self, client, monkeypatch):
        """Texto largo pero sin palabra del dominio (factura/cups/...) → 400."""
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        with patch("app.services.glosa_service.GlosaService._llamar_ia") as spy_llamar_ia:
            r = client.post(
                "/analizar",
                data=_form(
                    texto=(
                        "Este es un texto suficientemente largo pero sin "
                        "ninguna mención específica del dominio."
                    )
                ),
            )
            assert r.status_code == 400
            spy_llamar_ia.assert_not_called()

    def test_input_valido_pasa_la_pre_validacion(self, client, monkeypatch):
        """Input realista (≥60 chars + palabra del dominio) NO se bloquea
        en pre-validación (cualquier error posterior es de otra etapa)."""
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        texto_ok = (
            "TA0201 - Mayor valor cobrado en consulta especializada por "
            "valor objetado de $500.000 según factura electrónica FE-001"
        )
        # No espiamos IA — solo verificamos que el código pasa de la
        # pre-validación. Cualquier 500/422/etc no debe contener el mensaje
        # de "Texto de glosa muy corto".
        r = client.post("/analizar", data=_form(texto=texto_ok))
        # Puede fallar por otras razones (IA mockeada, etc.), pero NUNCA
        # con el mensaje del pre-validator.
        if r.status_code == 400:
            assert "corto" not in r.json().get("detail", "").lower()
            assert "mínimo" not in r.json().get("detail", "").lower()
