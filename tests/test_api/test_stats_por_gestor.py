"""Tests del endpoint /glosas/stats/por-gestor (R73 P1)."""
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
def usuario_coord():
    return UsuarioRecord(id=1, email="coord@hus.com", rol="COORDINADOR", activo=1)


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100_000, valor_aceptado=0,
        etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestStatsPorGestor:
    def test_sin_glosas(self, client):
        r = client.get("/glosas/stats/por-gestor")
        assert r.status_code == 200
        d = r.json()
        assert d["total_gestores_activos"] == 0

    def test_agrupa_por_auditor_email(self, client, db_session):
        # GestorA: 3 glosas, $300k objetado, $50k aceptado
        _seed(db_session, auditor_email="A@hus.com", valor_objetado=100_000, valor_aceptado=0)
        _seed(db_session, auditor_email="A@hus.com", valor_objetado=100_000, valor_aceptado=0)
        _seed(db_session, auditor_email="A@hus.com", valor_objetado=100_000, valor_aceptado=50_000)
        # GestorB: 1 glosa
        _seed(db_session, auditor_email="B@hus.com", valor_objetado=200_000)
        r = client.get("/glosas/stats/por-gestor")
        d = r.json()
        assert d["total_gestores_activos"] == 2
        a = next(x for x in d["items"] if x["auditor_email"] == "A@hus.com")
        assert a["count_glosas"] == 3
        assert a["valor_objetado"] == 300_000
        assert a["valor_aceptado"] == 50_000
        # tasa = 250/300 = 83.3
        assert abs(a["tasa_exito_pct"] - 83.3) < 0.5

    def test_orden_por_count_desc(self, client, db_session):
        for _ in range(4):
            _seed(db_session, auditor_email="A@hus.com")
        for _ in range(2):
            _seed(db_session, auditor_email="B@hus.com")
        r = client.get("/glosas/stats/por-gestor")
        items = r.json()["items"]
        assert items[0]["auditor_email"] == "A@hus.com"
        assert items[1]["auditor_email"] == "B@hus.com"

    def test_sin_auditor_email_no_aparece(self, client, db_session):
        _seed(db_session, auditor_email="X@hus.com")
        _seed(db_session, auditor_email=None)
        r = client.get("/glosas/stats/por-gestor")
        d = r.json()
        # Sin auditor_email se excluye
        assert d["total_gestores_activos"] == 1
