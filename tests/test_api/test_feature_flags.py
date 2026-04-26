"""Tests del endpoint GET /sistema/feature-flags (R144 P1)."""
from __future__ import annotations

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
def usuario_coord():
    return UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestFeatureFlags:
    def test_estructura(self, client):
        r = client.get("/sistema/feature-flags")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_flags", "activas", "inactivas", "items"):
            assert key in d
        # Mínimo 10 flags
        assert d["total_flags"] >= 10

    def test_flags_principales_presentes(self, client):
        r = client.get("/sistema/feature-flags")
        d = r.json()
        nombres = {f["nombre"] for f in d["items"]}
        for f in ("ia_anthropic", "ia_groq", "firma_digital_rsa",
                  "cifrado_simetrico", "smtp_alertas", "sentry",
                  "push_notifications", "whatsapp_business",
                  "telegram_bot"):
            assert f in nombres

    def test_cada_flag_tiene_metadata(self, client):
        r = client.get("/sistema/feature-flags")
        d = r.json()
        for f in d["items"]:
            assert "nombre" in f
            assert "activo" in f
            assert "descripcion" in f
            assert isinstance(f["activo"], bool)

    def test_consistencia_counts(self, client):
        r = client.get("/sistema/feature-flags")
        d = r.json()
        activas_real = sum(1 for f in d["items"] if f["activo"])
        assert d["activas"] == activas_real
        assert d["activas"] + d["inactivas"] == d["total_flags"]
