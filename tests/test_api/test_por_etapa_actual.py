"""Tests del endpoint GET /glosas/stats/por-etapa-actual (R147 P1)."""
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


def _seed(db, etapa, valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa=etapa, estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestPorEtapaActual:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/por-etapa-actual")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_orden_por_count_desc(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "RESPUESTA_PRIMERA")
        for _ in range(2):
            _seed(db_session, "RATIFICACION")
        _seed(db_session, "CONCILIACION")

        r = client.get("/glosas/stats/por-etapa-actual")
        d = r.json()
        etapas = [it["etapa"] for it in d["items"]]
        assert etapas[0] == "RESPUESTA_PRIMERA"
        assert d["items"][0]["count"] == 5

    def test_pct_consistente(self, client, db_session):
        # 8 etapa A + 2 etapa B → 80%/20%
        for _ in range(8):
            _seed(db_session, "A")
        for _ in range(2):
            _seed(db_session, "B")
        r = client.get("/glosas/stats/por-etapa-actual")
        d = r.json()
        items = {it["etapa"]: it for it in d["items"]}
        assert items["A"]["pct_del_total"] == 80.0
        assert items["B"]["pct_del_total"] == 20.0

    def test_acumula_valor(self, client, db_session):
        _seed(db_session, "X", valor=1000)
        _seed(db_session, "X", valor=2500)
        r = client.get("/glosas/stats/por-etapa-actual")
        d = r.json()
        assert d["items"][0]["valor_pendiente_total"] == 3500
