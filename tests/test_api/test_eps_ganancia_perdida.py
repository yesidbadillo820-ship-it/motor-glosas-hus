"""Tests del endpoint GET /glosas/stats/eps-ganancia-perdida (R282 P1)."""
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


def _seed(db, eps, estado, recuperado=0, aceptado=0):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_recuperado=recuperado,
        valor_aceptado=aceptado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestEPSGananciaPerdida:
    def test_calcula_balance(self, client, db_session):
        # SANITAS: 2 LEV con 1000 rec cada → ganancia 2000
        _seed(db_session, "SANITAS", "LEVANTADA", recuperado=1000)
        _seed(db_session, "SANITAS", "LEVANTADA", recuperado=1000)
        # SANITAS: 1 RAT con 500 aceptado → perdida 500
        _seed(db_session, "SANITAS", "RATIFICADA", aceptado=500)

        r = client.get(
            "/glosas/stats/eps-ganancia-perdida?min_glosas=1"
        )
        d = r.json()
        item = next(x for x in d["items"] if x["eps"] == "SANITAS")
        assert item["ganancia"] == 2000
        assert item["perdida"] == 500
        assert item["balance"] == 1500
        # ratio_ganancia: 2000 / 2500 = 80%
        assert item["ratio_ganancia_pct"] == 80.0

    def test_min_glosas_filtra(self, client, db_session):
        _seed(db_session, "POCAS", "LEVANTADA", recuperado=100)
        r = client.get(
            "/glosas/stats/eps-ganancia-perdida?min_glosas=5"
        )
        d = r.json()
        assert d["items"] == []
