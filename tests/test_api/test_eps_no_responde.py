"""Tests del endpoint GET /glosas/stats/eps-no-responde (R195 P1)."""
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


def _seed(db, eps, estado="RESPONDIDA", dias_atras=20, fecha_dec=None):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
        fecha_decision_eps=fecha_dec,
    ))
    db.commit()


class TestEPSNoResponde:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/eps-no-responde")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("umbral_dias", "total_eps_morosas", "items"):
            assert key in d

    def test_detecta_morosa(self, client, db_session):
        # SANITAS: 3 RESPONDIDAS hace 30d, sin fecha_decision
        for _ in range(3):
            _seed(db_session, "SANITAS", dias_atras=30)
        r = client.get("/glosas/stats/eps-no-responde?dias_minimos=15")
        d = r.json()
        assert d["items"][0]["eps"] == "SANITAS"
        assert d["items"][0]["count_sin_respuesta"] == 3

    def test_excluye_recientes(self, client, db_session):
        # Solo hace 5d → no aplica con dias_minimos=15
        _seed(db_session, "X", dias_atras=5)
        r = client.get("/glosas/stats/eps-no-responde?dias_minimos=15")
        d = r.json()
        assert d["items"] == []

    def test_excluye_si_eps_decidio(self, client, db_session):
        _seed(db_session, "X", dias_atras=30,
              fecha_dec=ahora_utc())
        r = client.get("/glosas/stats/eps-no-responde?dias_minimos=15")
        d = r.json()
        assert d["items"] == []

    def test_excluye_no_RESPONDIDA(self, client, db_session):
        _seed(db_session, "X", estado="RADICADA", dias_atras=30)
        r = client.get("/glosas/stats/eps-no-responde?dias_minimos=15")
        d = r.json()
        assert d["items"] == []
