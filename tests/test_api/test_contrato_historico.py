"""Tests del endpoint GET /contratos/{eps}/glosas-historico (R100 P1)."""
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


def _seed(db, eps, estado="RADICADA", **kw):
    base = dict(
        paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(eps=eps, estado=estado, **base))
    db.commit()


class TestContratoHistorico:
    def test_eps_sin_glosas(self, client):
        r = client.get("/contratos/SANITAS/glosas-historico")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_glosas"] == 0
        assert d["valor_objetado_total"] == 0
        assert d["top_5_codigos"] == []

    def test_metricas_basicas(self, client, db_session):
        _seed(db_session, "SANITAS", "LEVANTADA",
              valor_objetado=10000, valor_recuperado=10000)
        _seed(db_session, "SANITAS", "ACEPTADA",
              valor_objetado=5000, valor_recuperado=0)
        _seed(db_session, "SANITAS", "RADICADA",
              valor_objetado=3000)
        r = client.get("/contratos/SANITAS/glosas-historico")
        d = r.json()
        assert d["total_glosas"] == 3
        assert d["valor_objetado_total"] == 18000
        assert d["valor_recuperado_total"] == 10000
        assert d["decididas"] == 2  # LEVANTADA + ACEPTADA
        assert d["pendientes"] == 1
        # tasa_lev = 1/2 = 50%
        assert d["tasa_levantamiento_pct"] == 50.0

    def test_top_5_codigos(self, client, db_session):
        for c in ["TA0201", "TA0201", "TA0201", "FA0603", "FA0603", "AU0801"]:
            _seed(db_session, "SANITAS", codigo_glosa=c)
        r = client.get("/contratos/SANITAS/glosas-historico")
        d = r.json()
        top = d["top_5_codigos"]
        # TA0201 (3) > FA0603 (2) > AU0801 (1)
        assert top[0] == {"codigo": "TA0201", "veces": 3}
        assert top[1] == {"codigo": "FA0603", "veces": 2}
        assert top[2] == {"codigo": "AU0801", "veces": 1}

    def test_filtra_por_eps_estricto(self, client, db_session):
        _seed(db_session, "SANITAS", valor_objetado=1000)
        _seed(db_session, "NUEVA EPS", valor_objetado=999_999)
        r = client.get("/contratos/SANITAS/glosas-historico")
        d = r.json()
        assert d["total_glosas"] == 1
        assert d["valor_objetado_total"] == 1000
