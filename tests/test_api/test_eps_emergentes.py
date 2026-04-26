"""Tests del endpoint GET /glosas/stats/eps-emergentes (R120 P1)."""
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


def _seed(db, eps, dias_atras=0):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestEpsEmergentes:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/eps-emergentes")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []
        assert d["total_eps_nuevas"] == 0

    def test_eps_nueva_detectada(self, client, db_session):
        # SANITAS: histórica + actual → continua
        _seed(db_session, "SANITAS", dias_atras=60)
        _seed(db_session, "SANITAS", dias_atras=10)
        # NUEVA: solo en últimos 30d → emergente
        _seed(db_session, "RECIEN_LLEGADA", dias_atras=5)

        r = client.get("/glosas/stats/eps-emergentes?dias=30")
        d = r.json()
        assert d["total_eps_nuevas"] == 1
        assert d["items"][0]["eps"] == "RECIEN_LLEGADA"
        assert d["total_eps_continuas"] == 1  # SANITAS

    def test_eps_solo_historica_no_aparece(self, client, db_session):
        # EPS solo histórica (no en ventana) → ni nueva ni continua
        _seed(db_session, "VIEJA", dias_atras=100)
        r = client.get("/glosas/stats/eps-emergentes?dias=30")
        d = r.json()
        assert d["total_eps_nuevas"] == 0

    def test_orden_por_count_desc(self, client, db_session):
        # 3 nuevas con distintos counts
        for _ in range(5):
            _seed(db_session, "NUEVA_A", dias_atras=5)
        for _ in range(2):
            _seed(db_session, "NUEVA_B", dias_atras=5)
        _seed(db_session, "NUEVA_C", dias_atras=5)

        r = client.get("/glosas/stats/eps-emergentes")
        d = r.json()
        nombres = [it["eps"] for it in d["items"]]
        assert nombres == ["NUEVA_A", "NUEVA_B", "NUEVA_C"]

    def test_acumula_valor_objetado(self, client, db_session):
        _seed(db_session, "NUEVA", dias_atras=5)
        _seed(db_session, "NUEVA", dias_atras=5)
        r = client.get("/glosas/stats/eps-emergentes")
        d = r.json()
        item = d["items"][0]
        assert item["valor_objetado_total"] == 2000
