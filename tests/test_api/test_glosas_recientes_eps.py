"""Tests del endpoint GET /glosas/stats/glosas-recientes-eps (R288 P1)."""
from __future__ import annotations

from datetime import timedelta

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


def _seed(db, glosa_id, eps, dias_atras=0):
    db.add(GlosaRecord(
        id=glosa_id,
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestGlosasRecientesEPS:
    def test_filtra_y_ordena(self, client, db_session):
        _seed(db_session, 1, "SANITAS", dias_atras=10)
        _seed(db_session, 2, "SANITAS", dias_atras=2)
        _seed(db_session, 3, "OTRA", dias_atras=1)

        r = client.get(
            "/glosas/stats/glosas-recientes-eps?eps=SANITAS"
        )
        d = r.json()
        assert d["eps"] == "SANITAS"
        assert len(d["items"]) == 2
        # Más reciente primero (id=2 con dias_atras=2)
        assert d["items"][0]["glosa_id"] == 2

    def test_limit(self, client, db_session):
        for i in range(5):
            _seed(db_session, i + 1, "XX")
        r = client.get(
            "/glosas/stats/glosas-recientes-eps?eps=XX&limit=2"
        )
        d = r.json()
        assert len(d["items"]) == 2
