"""Tests del endpoint GET /glosas/stats/codigo-respuesta-tendencia (R286 P1)."""
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


def _seed(db, codigo, dias_atras=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="LEVANTADA",
        creado_en=ahora_utc() - timedelta(days=dias_atras),
        codigo_respuesta=codigo,
    ))
    db.commit()


class TestCodigoRespuestaTendencia:
    def test_emergente(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "RE9501", dias_atras=5)

        r = client.get(
            "/glosas/stats/codigo-respuesta-tendencia"
            "?dias=30&min_glosas_actual=3"
        )
        d = r.json()
        assert len(d["items"]) == 1
        assert d["items"][0]["codigo_respuesta"] == "RE9501"
        assert d["items"][0]["count_previo"] == 0
        assert d["items"][0]["delta_pct"] == 100.0

    def test_min_glosas_filtra(self, client, db_session):
        _seed(db_session, "RE9701", dias_atras=5)
        r = client.get(
            "/glosas/stats/codigo-respuesta-tendencia"
            "?min_glosas_actual=5"
        )
        d = r.json()
        assert d["items"] == []
