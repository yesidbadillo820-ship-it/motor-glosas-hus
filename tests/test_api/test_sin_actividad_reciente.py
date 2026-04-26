"""Tests del endpoint GET /glosas/stats/sin-actividad-reciente (R298 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    AuditLogRecord,
    GlosaRecord,
    UsuarioRecord,
)


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


def _seed_glosa(db, glosa_id, valor=1000):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_audit(db, glosa_id, dias_atras=0):
    db.add(AuditLogRecord(
        timestamp=ahora_utc() - timedelta(days=dias_atras),
        usuario_email="x", accion="UPDATE",
        tabla="historial", registro_id=glosa_id,
    ))
    db.commit()


class TestSinActividadReciente:
    def test_filtra_con_actividad(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        # Glosa 1 tiene actividad reciente
        _seed_audit(db_session, 1, dias_atras=5)
        # Glosa 2 no tiene actividad

        r = client.get(
            "/glosas/stats/sin-actividad-reciente?dias=30"
        )
        d = r.json()
        assert d["total_estancadas"] == 1
        assert d["items"][0]["glosa_id"] == 2

    def test_actividad_antigua_no_cuenta(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_audit(db_session, 1, dias_atras=100)
        r = client.get(
            "/glosas/stats/sin-actividad-reciente?dias=30"
        )
        d = r.json()
        assert d["total_estancadas"] == 1
