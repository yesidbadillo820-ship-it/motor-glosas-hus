"""Tests del endpoint GET /glosas/stats/antiguedad-promedio-eps (R214 P1)."""
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


def _seed(db, eps, dias_atras, estado="RADICADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestAntiguedadPromedioEPS:
    def test_promedio_y_max(self, client, db_session):
        # SANITAS: glosas hace 30, 60, 90 días → promedio 60, max 90
        _seed(db_session, "SANITAS", 30)
        _seed(db_session, "SANITAS", 60)
        _seed(db_session, "SANITAS", 90)
        # OTRA: glosa hace 10 días
        _seed(db_session, "OTRA", 10)

        r = client.get("/glosas/stats/antiguedad-promedio-eps")
        d = r.json()
        items = {it["eps"]: it for it in d["items"]}
        assert items["SANITAS"]["antiguedad_promedio_dias"] == 60.0
        assert items["SANITAS"]["antiguedad_max_dias"] == 90
        assert items["OTRA"]["antiguedad_promedio_dias"] == 10.0

    def test_orden_desc(self, client, db_session):
        _seed(db_session, "VIEJA", 100)
        _seed(db_session, "NUEVA", 5)
        r = client.get("/glosas/stats/antiguedad-promedio-eps")
        d = r.json()
        assert d["items"][0]["eps"] == "VIEJA"
        assert d["items"][1]["eps"] == "NUEVA"

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, "X", 100, estado="LEVANTADA")
        r = client.get("/glosas/stats/antiguedad-promedio-eps")
        d = r.json()
        assert d["items"] == []
