"""Tests del endpoint GET /glosas/stats/eps-velocidad-respuesta (R218 P1)."""
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


def _seed(db, eps, dias_creacion_to_decision):
    cre = ahora_utc() - timedelta(days=dias_creacion_to_decision + 30)
    dec = cre + timedelta(days=dias_creacion_to_decision)
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="LEVANTADA",
        creado_en=cre,
        fecha_decision_eps=dec,
    ))
    db.commit()


class TestEPSVelocidadRespuesta:
    def test_orden_asc(self, client, db_session):
        # SANITAS: 30d en promedio (rápida)
        _seed(db_session, "SANITAS", 30)
        _seed(db_session, "SANITAS", 30)
        _seed(db_session, "SANITAS", 30)
        # NUEVA: 90d en promedio (lenta)
        _seed(db_session, "NUEVA", 90)
        _seed(db_session, "NUEVA", 90)
        _seed(db_session, "NUEVA", 90)

        r = client.get(
            "/glosas/stats/eps-velocidad-respuesta?min_glosas=1"
        )
        d = r.json()
        # SANITAS más rápida → primera
        assert d["items"][0]["eps"] == "SANITAS"
        assert d["items"][0]["tiempo_promedio_dias"] == 30.0

    def test_filtro_min(self, client, db_session):
        _seed(db_session, "POCAS", 10)
        _seed(db_session, "POCAS", 10)
        r = client.get(
            "/glosas/stats/eps-velocidad-respuesta?min_glosas=3"
        )
        d = r.json()
        assert d["items"] == []

    def test_excluye_sin_decision(self, client, db_session):
        # Glosa sin fecha_decision → no cuenta
        db_session.add(GlosaRecord(
            eps="X", paciente="X", codigo_glosa="C",
            valor_objetado=1000, etapa="X", estado="RADICADA",
            creado_en=ahora_utc(),
            fecha_decision_eps=None,
        ))
        db_session.commit()
        r = client.get(
            "/glosas/stats/eps-velocidad-respuesta?min_glosas=1"
        )
        d = r.json()
        assert d["items"] == []
