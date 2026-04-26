"""Tests del endpoint GET /glosas/stats/cumplimiento-sla-mensual (R335 P1)."""
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


def _seed(db, a_tiempo, estado="LEVANTADA"):
    dec = ahora_utc()
    venc = dec + timedelta(days=5) if a_tiempo else dec - timedelta(days=5)
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=dec,
        fecha_vencimiento=venc,
    ))
    db.commit()


class TestCumplimientoSLAMensual:
    def test_calcula_pct(self, client, db_session):
        _seed(db_session, a_tiempo=True)
        _seed(db_session, a_tiempo=True)
        _seed(db_session, a_tiempo=False)
        # 2/3 a tiempo → 66.67%

        r = client.get("/glosas/stats/cumplimiento-sla-mensual")
        d = r.json()
        assert len(d["serie"]) == 1
        mes = d["serie"][0]
        assert mes["total_cerradas"] == 3
        assert mes["cerradas_a_tiempo"] == 2
        assert mes["cumplimiento_sla_pct"] == 66.67

    def test_vacio(self, client):
        r = client.get("/glosas/stats/cumplimiento-sla-mensual")
        d = r.json()
        assert d["serie"] == []
