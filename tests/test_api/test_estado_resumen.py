"""Tests del endpoint GET /glosas/{id}/estado-resumen (R251 P1)."""
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


def _seed(db, gid=1):
    db.add(GlosaRecord(
        id=gid, eps="SANITAS", paciente="X", codigo_glosa="C",
        valor_objetado=15000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        dias_restantes=5,
    ))
    db.commit()


class TestEstadoResumen:
    def test_404(self, client):
        r = client.get("/glosas/99999/estado-resumen")
        assert r.status_code == 404

    def test_estructura(self, client, db_session):
        _seed(db_session, 1)
        r = client.get("/glosas/1/estado-resumen")
        d = r.json()
        for key in ("id", "eps", "valor_objetado", "estado",
                    "dias_restantes"):
            assert key in d
        assert d["id"] == 1
        assert d["eps"] == "SANITAS"
        assert d["valor_objetado"] == 15000
