"""Tests del endpoint GET /glosas/stats/codigo-glosa-tendencia (R260 P1)."""
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
        eps="X", paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestCodigoTendencia:
    def test_emergente(self, client, db_session):
        # Codigo A: 5 actuales, 0 previas → 100%
        for _ in range(5):
            _seed(db_session, "TA0801", dias_atras=5)

        r = client.get(
            "/glosas/stats/codigo-glosa-tendencia"
            "?dias=30&min_glosas_actual=3"
        )
        d = r.json()
        assert len(d["items"]) == 1
        assert d["items"][0]["codigo_glosa"] == "TA0801"
        assert d["items"][0]["count_previo"] == 0
        assert d["items"][0]["delta_pct"] == 100.0

    def test_en_declive(self, client, db_session):
        # Codigo X: 4 actuales, 8 previos → -50%
        for _ in range(4):
            _seed(db_session, "FA0603", dias_atras=10)
        for _ in range(8):
            _seed(db_session, "FA0603", dias_atras=40)

        r = client.get(
            "/glosas/stats/codigo-glosa-tendencia"
            "?dias=30&min_glosas_actual=3"
        )
        d = r.json()
        item = next(x for x in d["items"] if x["codigo_glosa"] == "FA0603")
        assert item["count_actual"] == 4
        assert item["count_previo"] == 8
        assert item["delta_pct"] == -50.0

    def test_min_glosas_actual_filtra(self, client, db_session):
        _seed(db_session, "RA0001", dias_atras=5)  # solo 1 actual
        r = client.get(
            "/glosas/stats/codigo-glosa-tendencia"
            "?dias=30&min_glosas_actual=3"
        )
        d = r.json()
        assert d["items"] == []
