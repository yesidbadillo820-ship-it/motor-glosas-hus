"""Tests del endpoint GET /glosas/stats/eps-tiempo-radicacion-objecion (R333 P1)."""
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


def _seed(db, eps, dias_objecion_despues_radicacion):
    rad = ahora_utc() - timedelta(
        days=dias_objecion_despues_radicacion + 30,
    )
    obj = rad + timedelta(days=dias_objecion_despues_radicacion)
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        fecha_radicacion_factura=rad,
        fecha_objecion_eps=obj,
    ))
    db.commit()


class TestEPSTiempoRadObj:
    def test_promedio(self, client, db_session):
        _seed(db_session, "X", 10)
        _seed(db_session, "X", 20)
        _seed(db_session, "X", 30)

        r = client.get(
            "/glosas/stats/eps-tiempo-radicacion-objecion?min_glosas=1"
        )
        d = r.json()
        item = d["items"][0]
        assert item["eps"] == "X"
        assert item["count"] == 3
        assert item["tiempo_promedio_dias"] == 20.0
        assert item["tiempo_max_dias"] == 30
