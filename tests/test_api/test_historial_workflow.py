"""Tests del endpoint GET /glosas/{id}/historial-workflow (R134 P2)."""
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


def _seed_glosa(db, gid=1, estado="RADICADA"):
    db.add(GlosaRecord(
        id=gid, eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()
    return gid


def _seed_audit(db, gid, campo, anterior, nuevo, hr_atras=1):
    db.add(AuditLogRecord(
        usuario_email="u@x", accion="UPDATE",
        tabla="glosas", registro_id=gid,
        campo=campo, valor_anterior=anterior, valor_nuevo=nuevo,
        timestamp=ahora_utc() - timedelta(hours=hr_atras),
    ))
    db.commit()


class TestHistorialWorkflow:
    def test_404(self, client):
        r = client.get("/glosas/99999/historial-workflow")
        assert r.status_code == 404

    def test_glosa_sin_transiciones(self, client, db_session):
        gid = _seed_glosa(db_session)
        r = client.get(f"/glosas/{gid}/historial-workflow")
        d = r.json()
        assert d["total_transiciones"] == 0
        assert d["items"] == []

    def test_filtra_solo_estado_y_workflow(self, client, db_session):
        gid = _seed_glosa(db_session)
        # Cambio de estado → debe aparecer
        _seed_audit(db_session, gid, "estado", "RADICADA", "RESPONDIDA")
        # Cambio de workflow_state → debe aparecer
        _seed_audit(db_session, gid, "workflow_state",
                    "RADICADA", "RESPONDIDA")
        # Cambio de otro campo → NO debe aparecer
        _seed_audit(db_session, gid, "valor_objetado", "1000", "2000")
        # Audit en otra tabla → NO debe aparecer
        db_session.add(AuditLogRecord(
            usuario_email="u@x", tabla="usuarios", registro_id=gid,
            campo="estado", timestamp=ahora_utc(),
        ))
        db_session.commit()

        r = client.get(f"/glosas/{gid}/historial-workflow")
        d = r.json()
        assert d["total_transiciones"] == 2
        campos = [it["campo"] for it in d["items"]]
        assert set(campos) == {"estado", "workflow_state"}

    def test_orden_ascendente(self, client, db_session):
        gid = _seed_glosa(db_session)
        _seed_audit(db_session, gid, "estado", "A", "B", hr_atras=10)
        _seed_audit(db_session, gid, "estado", "B", "C", hr_atras=2)
        _seed_audit(db_session, gid, "estado", "C", "D", hr_atras=5)
        r = client.get(f"/glosas/{gid}/historial-workflow")
        d = r.json()
        timestamps = [it["timestamp"] for it in d["items"]]
        assert timestamps == sorted(timestamps)

    def test_aislamiento_entre_glosas(self, client, db_session):
        _seed_glosa(db_session, gid=1)
        _seed_glosa(db_session, gid=2)
        _seed_audit(db_session, 1, "estado", "A", "B")
        _seed_audit(db_session, 2, "estado", "X", "Y")

        r = client.get("/glosas/1/historial-workflow")
        d = r.json()
        assert d["total_transiciones"] == 1
        assert d["items"][0]["valor_anterior"] == "A"
