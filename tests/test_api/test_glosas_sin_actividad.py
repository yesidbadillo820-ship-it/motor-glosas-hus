"""Tests del endpoint GET /glosas/sin-actividad (R99 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AuditLogRecord, GlosaRecord, UsuarioRecord


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


def _seed_glosa(db, dias_atras=0, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


def _seed_audit(db, glosa_id, dias_atras):
    db.add(AuditLogRecord(
        usuario_email="u@x", accion="UPDATE", tabla="glosas",
        registro_id=glosa_id,
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestGlosasSinActividad:
    def test_vacio(self, client):
        r = client.get("/glosas/sin-actividad")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_sin_actividad"] == 0

    def test_glosa_reciente_no_aparece(self, client, db_session):
        _seed_glosa(db_session, dias_atras=5)
        r = client.get("/glosas/sin-actividad")  # umbral 15d
        d = r.json()
        assert d["total_sin_actividad"] == 0

    def test_glosa_vieja_aparece(self, client, db_session):
        g = _seed_glosa(db_session, dias_atras=30)
        r = client.get("/glosas/sin-actividad")
        d = r.json()
        assert d["total_sin_actividad"] == 1
        assert d["items"][0]["id"] == g.id
        assert d["items"][0]["dias_sin_movimiento"] >= 30

    def test_audit_reciente_rescata_glosa_vieja(self, client, db_session):
        # Glosa creada hace 30d pero con audit log de hace 5d
        g = _seed_glosa(db_session, dias_atras=30)
        _seed_audit(db_session, g.id, dias_atras=5)
        r = client.get("/glosas/sin-actividad")
        d = r.json()
        # No debe aparecer porque hay actividad reciente
        assert d["total_sin_actividad"] == 0

    def test_excluye_cerradas(self, client, db_session):
        # Vieja pero cerrada → no aparece
        _seed_glosa(db_session, dias_atras=100, estado="ACEPTADA")
        _seed_glosa(db_session, dias_atras=100, estado="LEVANTADA")
        r = client.get("/glosas/sin-actividad")
        d = r.json()
        assert d["total_sin_actividad"] == 0

    def test_umbral_custom(self, client, db_session):
        _seed_glosa(db_session, dias_atras=10)
        # Con umbral 5d aparece, con 30d no
        r = client.get("/glosas/sin-actividad?dias=5")
        assert r.json()["total_sin_actividad"] == 1
        r = client.get("/glosas/sin-actividad?dias=30")
        assert r.json()["total_sin_actividad"] == 0

    def test_orden_mas_olvidadas_primero(self, client, db_session):
        _seed_glosa(db_session, dias_atras=20)
        _seed_glosa(db_session, dias_atras=80)
        _seed_glosa(db_session, dias_atras=40)
        r = client.get("/glosas/sin-actividad")
        d = r.json()
        dias_list = [it["dias_sin_movimiento"] for it in d["items"]]
        assert dias_list == sorted(dias_list, reverse=True)
