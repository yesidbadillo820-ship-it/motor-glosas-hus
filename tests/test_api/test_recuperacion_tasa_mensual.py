"""Tests del endpoint GET /glosas/stats/recuperacion-tasa-mensual (R311 P1)."""
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


def _seed(db, valor_obj, valor_rec, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor_obj, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=ahora_utc(),
    ))
    db.commit()


class TestRecuperacionTasaMensual:
    def test_calcula(self, client, db_session):
        _seed(db_session, valor_obj=10000, valor_rec=8000)
        _seed(db_session, valor_obj=5000, valor_rec=2000)
        # Total: 15000 obj, 10000 rec → 66.67%

        r = client.get(
            "/glosas/stats/recuperacion-tasa-mensual?meses=2"
        )
        d = r.json()
        assert len(d["serie"]) == 1
        mes = d["serie"][0]
        assert mes["valor_objetado"] == 15000
        assert mes["valor_recuperado"] == 10000
        assert mes["tasa_recuperacion_pct"] == 66.67

    def test_vacio(self, client):
        r = client.get(
            "/glosas/stats/recuperacion-tasa-mensual"
        )
        d = r.json()
        assert d["serie"] == []
