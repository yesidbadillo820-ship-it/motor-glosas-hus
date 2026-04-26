"""Tests del endpoint GET /glosas/stats/aging-glosas (R237 P1)."""
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


def _seed(db, dias_atras, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestAgingGlosas:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/aging-glosas")
        d = r.json()
        # 5 buckets
        assert len(d["items"]) == 5

    def test_clasificacion(self, client, db_session):
        _seed(db_session, 10)   # 0-30
        _seed(db_session, 45)   # 31-60
        _seed(db_session, 75)   # 61-90
        _seed(db_session, 120)  # 91-180
        _seed(db_session, 250)  # >180

        r = client.get("/glosas/stats/aging-glosas")
        d = r.json()
        items = {it["rango_dias"]: it for it in d["items"]}
        assert items["0-30"]["count"] == 1
        assert items["31-60"]["count"] == 1
        assert items["61-90"]["count"] == 1
        assert items["91-180"]["count"] == 1
        assert items[">180"]["count"] == 1

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, 10, estado="LEVANTADA")
        r = client.get("/glosas/stats/aging-glosas")
        d = r.json()
        assert d["total_abiertas"] == 0
