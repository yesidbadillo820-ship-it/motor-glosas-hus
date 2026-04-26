"""Tests del endpoint GET /glosas/stats/picos-historicos (R104 P2)."""
from __future__ import annotations

from datetime import datetime, timezone

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


def _seed(db, fecha, valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=fecha,
    ))
    db.commit()


class TestPicosHistoricos:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/picos-historicos")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_dias_con_actividad"] == 0
        assert d["items"] == []

    def test_orden_por_glosas_desc(self, client, db_session):
        # 2026-04-10: 5 glosas
        for _ in range(5):
            _seed(db_session, datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc))
        # 2026-04-15: 10 glosas (pico)
        for _ in range(10):
            _seed(db_session, datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc))
        # 2026-04-12: 2 glosas
        for _ in range(2):
            _seed(db_session, datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc))

        r = client.get("/glosas/stats/picos-historicos")
        d = r.json()
        assert d["items"][0]["fecha"] == "2026-04-15"
        assert d["items"][0]["glosas"] == 10
        assert d["items"][1]["fecha"] == "2026-04-10"
        assert d["items"][2]["fecha"] == "2026-04-12"

    def test_acumula_valor(self, client, db_session):
        _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc),
              valor=1000)
        _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc),
              valor=2500)
        r = client.get("/glosas/stats/picos-historicos")
        d = r.json()
        assert d["items"][0]["valor_total"] == 3500

    def test_top_limita(self, client, db_session):
        for d_offset in range(15):
            _seed(db_session, datetime(2026, 4, d_offset+1,
                                        tzinfo=timezone.utc))
        r = client.get("/glosas/stats/picos-historicos?top=5")
        d = r.json()
        assert len(d["items"]) == 5
        assert d["total_dias_con_actividad"] == 15
