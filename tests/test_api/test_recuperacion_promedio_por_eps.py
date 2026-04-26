"""Tests del endpoint GET /glosas/stats/recuperacion-promedio-por-eps (R182 P1)."""
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


def _seed(db, eps, valor_obj=1000, valor_rec=500, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor_obj, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestRecuperacionPromedioPorEPS:
    def test_excluye_abiertas(self, client, db_session):
        _seed(db_session, "X", estado="RADICADA")
        r = client.get(
            "/glosas/stats/recuperacion-promedio-por-eps?min_glosas=1"
        )
        d = r.json()
        assert d["items"] == []

    def test_promedio(self, client, db_session):
        # SANITAS: 2 glosas con $5k y $3k recuperado → promedio $4k
        _seed(db_session, "SANITAS", valor_rec=5000)
        _seed(db_session, "SANITAS", valor_rec=3000)
        _seed(db_session, "SANITAS", valor_rec=0,
              estado="ACEPTADA")  # no recuperó
        r = client.get(
            "/glosas/stats/recuperacion-promedio-por-eps?min_glosas=1"
        )
        d = r.json()
        item = d["items"][0]
        # 8000 / 3 = 2666.67
        assert 2600 < item["valor_recuperado_promedio"] < 2700

    def test_filtro_min_glosas(self, client, db_session):
        _seed(db_session, "POCAS", valor_rec=1000)
        _seed(db_session, "POCAS", valor_rec=1000)
        r = client.get(
            "/glosas/stats/recuperacion-promedio-por-eps?min_glosas=3"
        )
        d = r.json()
        assert d["items"] == []

    def test_orden_promedio_desc(self, client, db_session):
        # ALTA: $10k promedio
        _seed(db_session, "ALTA", valor_rec=10000)
        _seed(db_session, "ALTA", valor_rec=10000)
        # BAJA: $1k promedio
        _seed(db_session, "BAJA", valor_rec=1000)
        _seed(db_session, "BAJA", valor_rec=1000)

        r = client.get(
            "/glosas/stats/recuperacion-promedio-por-eps?min_glosas=1"
        )
        d = r.json()
        assert d["items"][0]["eps"] == "ALTA"
        assert d["items"][1]["eps"] == "BAJA"
