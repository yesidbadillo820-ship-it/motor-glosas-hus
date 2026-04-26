"""Tests del endpoint GET /sistema/limites (R110 P1)."""
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


class TestSistemaLimites:
    def test_estructura(self, client):
        r = client.get("/sistema/limites")
        assert r.status_code == 200, r.text
        d = r.json()
        for sec in ("rate_limit_ia", "export_limits", "upload_limits",
                    "search_limits", "retention", "ui_limits"):
            assert sec in d

    def test_rate_limit_ia_tiene_quotas(self, client):
        r = client.get("/sistema/limites")
        d = r.json()
        assert d["rate_limit_ia"]["calls_por_dia_por_usuario"] > 0
        assert d["rate_limit_ia"]["calls_por_hora_por_usuario"] > 0

    def test_export_limits_audit_50k(self, client):
        r = client.get("/sistema/limites")
        d = r.json()
        assert d["export_limits"]["audit_csv_max_filas"] == 50_000

    def test_retention_periodos(self, client):
        r = client.get("/sistema/limites")
        d = r.json()
        assert d["retention"]["ai_cache_dias"] == 30
        assert d["retention"]["ai_calls_dias"] == 90
        assert d["retention"]["papelera_dias"] == 30
