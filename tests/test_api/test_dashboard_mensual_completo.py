"""Tests del endpoint GET /glosas/stats/dashboard-mensual-completo (R350 P1 — hito)."""
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


def _seed(db, eps="X", gestor=None, estado="RADICADA",
          obj=1000, rec=0, decidida=False):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=obj, valor_recuperado=rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        fecha_decision_eps=ahora_utc() if decidida else None,
    ))
    db.commit()


class TestDashboardMensualCompleto:
    def test_estructura(self, client):
        r = client.get(
            "/glosas/stats/dashboard-mensual-completo"
        )
        d = r.json()
        for k in (
            "mes", "kpis_creacion", "kpis_decisiones",
            "kpis_sla", "tasa_levantamiento_pct",
            "tasa_recuperacion_monetaria_pct",
            "top_3_eps_volumen", "top_3_gestores_volumen",
        ):
            assert k in d

    def test_kpis(self, client, db_session):
        _seed(
            db_session, eps="SANITAS", gestor="Alice",
            estado="LEVANTADA", obj=10000, rec=8000,
            decidida=True,
        )
        _seed(
            db_session, eps="SANITAS", gestor="Bob",
            estado="RADICADA",
        )

        r = client.get(
            "/glosas/stats/dashboard-mensual-completo"
        )
        d = r.json()
        assert d["kpis_creacion"]["creadas"] == 2
        assert d["kpis_decisiones"]["decididas"] == 1
        assert d["kpis_decisiones"]["levantadas"] == 1
        assert d["tasa_levantamiento_pct"] == 100.0
        assert d["tasa_recuperacion_monetaria_pct"] == 80.0
