"""Tests del endpoint GET /glosas/{id}/whatsapp-mensaje (R179 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord


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


def _seed(db, **kw):
    base = dict(
        id=1, eps="SANITAS", paciente="X", codigo_glosa="TA0201",
        factura="F-123", valor_objetado=15000,
        etapa="X", estado="RADICADA", dias_restantes=5,
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestWhatsappMensaje:
    def test_404(self, client):
        r = client.get("/glosas/99999/whatsapp-mensaje")
        assert r.status_code == 404

    def test_estructura(self, client, db_session):
        _seed(db_session)
        r = client.get("/glosas/1/whatsapp-mensaje")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("glosa_id", "mensaje_whatsapp", "longitud_chars"):
            assert key in d

    def test_mensaje_incluye_datos(self, client, db_session):
        _seed(db_session, eps="SANITAS", codigo_glosa="TA0201",
              valor_objetado=15000)
        r = client.get("/glosas/1/whatsapp-mensaje")
        msg = r.json()["mensaje_whatsapp"]
        assert "SANITAS" in msg
        assert "TA0201" in msg
        assert "15,000" in msg
        assert "F-123" in msg

    def test_urgencia_vencida(self, client, db_session):
        _seed(db_session, dias_restantes=-10)
        r = client.get("/glosas/1/whatsapp-mensaje")
        msg = r.json()["mensaje_whatsapp"]
        assert "VENCIDA" in msg

    def test_urgencia_critica(self, client, db_session):
        _seed(db_session, dias_restantes=2)
        r = client.get("/glosas/1/whatsapp-mensaje")
        msg = r.json()["mensaje_whatsapp"]
        assert "CRITICA" in msg

    def test_urgencia_en_tiempo(self, client, db_session):
        _seed(db_session, dias_restantes=20)
        r = client.get("/glosas/1/whatsapp-mensaje")
        msg = r.json()["mensaje_whatsapp"]
        assert "EN TIEMPO" in msg
