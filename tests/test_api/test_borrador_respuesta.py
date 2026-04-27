"""Tests del endpoint GET /glosas/{id}/borrador-respuesta (R395 P1)."""
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
    return UsuarioRecord(id=1, email="x@x", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gid, eps="X", codigo="C", estado="RADICADA",
          dictamen=None):
    db.add(GlosaRecord(
        id=gid,
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dictamen=dictamen,
        fecha_decision_eps=(
            ahora_utc() if estado != "RADICADA" else None
        ),
    ))
    db.commit()


class TestBorradorRespuesta:
    def test_con_caso_levantado(self, db_session, client):
        _seed(db_session, 1)  # glosa actual
        _seed(
            db_session, 100, estado="LEVANTADA",
            dictamen="Dictamen ganador detallado",
        )
        r = client.get("/glosas/1/borrador-respuesta")
        d = r.json()
        assert d["borrador_disponible"] is True
        assert d["fuente_caso_id"] == 100
        assert "ganador" in d["borrador"]

    def test_sin_caso(self, db_session, client):
        _seed(db_session, 1)
        r = client.get("/glosas/1/borrador-respuesta")
        d = r.json()
        assert d["borrador_disponible"] is False

    def test_404(self, client):
        r = client.get("/glosas/999/borrador-respuesta")
        assert r.status_code == 404
