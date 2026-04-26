"""Tests del endpoint GET /glosas/{id}/casos-similares-resueltos (R349 P1)."""
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


def _seed(db, glosa_id, eps, codigo, estado="RADICADA",
          dictamen=None):
    db.add(GlosaRecord(
        id=glosa_id,
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=ahora_utc() if estado != "RADICADA" else None,
        dictamen=dictamen,
    ))
    db.commit()


class TestCasosSimilaresResueltos:
    def test_match(self, client, db_session):
        # Glosa abierta
        _seed(db_session, 1, "X", "TA01", estado="RADICADA")
        # Casos similares decididos
        _seed(
            db_session, 2, "X", "TA01", estado="LEVANTADA",
            dictamen="argumento ganador",
        )
        _seed(
            db_session, 3, "X", "TA01", estado="RATIFICADA",
        )
        # Glosa de otra EPS, no debe aparecer
        _seed(
            db_session, 4, "OTRA", "TA01", estado="LEVANTADA",
        )

        r = client.get("/glosas/1/casos-similares-resueltos")
        d = r.json()
        assert d["total_casos_similares"] == 2

    def test_404(self, client):
        r = client.get("/glosas/999/casos-similares-resueltos")
        assert r.status_code == 404
