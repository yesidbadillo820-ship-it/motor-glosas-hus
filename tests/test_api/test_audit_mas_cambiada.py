"""Tests del endpoint GET /glosas/stats/audit-mas-cambiada (R211 P1)."""
from __future__ import annotations

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


def _seed_glosa(db, gid):
    db.add(GlosaRecord(
        id=gid, eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_audit(db, glosa_id, tabla="glosas"):
    db.add(AuditLogRecord(
        usuario_email="u@x", accion="UPDATE",
        tabla=tabla, registro_id=glosa_id,
        timestamp=ahora_utc(),
    ))
    db.commit()


class TestAuditMasCambiada:
    def test_orden_desc(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        # Glosa 1: 7 eventos
        for _ in range(7):
            _seed_audit(db_session, 1)
        # Glosa 2: 3 eventos
        for _ in range(3):
            _seed_audit(db_session, 2)

        r = client.get("/glosas/stats/audit-mas-cambiada")
        d = r.json()
        assert d["items"][0]["glosa_id"] == 1
        assert d["items"][0]["n_eventos_audit"] == 7
        assert d["items"][1]["glosa_id"] == 2

    def test_excluye_otra_tabla(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_audit(db_session, 1, tabla="glosas")
        # Audit de otra tabla con mismo registro_id → no
        _seed_audit(db_session, 1, tabla="usuarios")

        r = client.get("/glosas/stats/audit-mas-cambiada")
        d = r.json()
        assert d["items"][0]["n_eventos_audit"] == 1
