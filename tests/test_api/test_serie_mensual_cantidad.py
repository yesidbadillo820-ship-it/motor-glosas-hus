"""Tests del endpoint GET /glosas/stats/serie-mensual-cantidad (R124 P2)."""
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


def _seed(db, creado, estado="RADICADA", fecha_dec=None):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=creado, fecha_decision_eps=fecha_dec,
    ))
    db.commit()


class TestSerieMensualCantidad:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/serie-mensual-cantidad")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["serie"] == []

    def test_creadas_y_cerradas_separadas(self, client, db_session):
        # Glosa creada en marzo, cerrada en abril
        _seed(db_session,
              creado=datetime(2026, 3, 15, tzinfo=timezone.utc),
              estado="LEVANTADA",
              fecha_dec=datetime(2026, 4, 5, tzinfo=timezone.utc))

        r = client.get("/glosas/stats/serie-mensual-cantidad?meses=24")
        d = r.json()
        meses = {s["mes"]: s for s in d["serie"]}
        # Marzo: 1 creada, 0 cerradas
        assert meses["2026-03"]["creadas"] == 1
        assert meses["2026-03"]["cerradas"] == 0
        # Abril: 0 creadas, 1 cerrada
        assert meses["2026-04"]["creadas"] == 0
        assert meses["2026-04"]["cerradas"] == 1

    def test_delta_neto(self, client, db_session):
        # Abril: 3 creadas, 1 cerrada → delta = +2
        for _ in range(3):
            _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc))
        _seed(db_session,
              creado=datetime(2026, 3, 1, tzinfo=timezone.utc),
              estado="LEVANTADA",
              fecha_dec=datetime(2026, 4, 15, tzinfo=timezone.utc))

        r = client.get("/glosas/stats/serie-mensual-cantidad?meses=24")
        d = r.json()
        abril = next(s for s in d["serie"] if s["mes"] == "2026-04")
        assert abril["creadas"] == 3
        assert abril["cerradas"] == 1
        assert abril["delta_neto"] == 2

    def test_ratio_cierre(self, client, db_session):
        # 4 creadas en abril, 2 cerradas en abril → ratio = 0.5
        for _ in range(4):
            _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc))
        for _ in range(2):
            _seed(db_session,
                  creado=datetime(2026, 3, 1, tzinfo=timezone.utc),
                  estado="LEVANTADA",
                  fecha_dec=datetime(2026, 4, 15, tzinfo=timezone.utc))

        r = client.get("/glosas/stats/serie-mensual-cantidad?meses=24")
        d = r.json()
        abril = next(s for s in d["serie"] if s["mes"] == "2026-04")
        assert abril["ratio_cierre"] == 0.5

    def test_serie_ordenada_ascendente(self, client, db_session):
        _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 1, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 3, 1, tzinfo=timezone.utc))
        r = client.get("/glosas/stats/serie-mensual-cantidad?meses=24")
        d = r.json()
        meses = [s["mes"] for s in d["serie"]]
        assert meses == sorted(meses)
