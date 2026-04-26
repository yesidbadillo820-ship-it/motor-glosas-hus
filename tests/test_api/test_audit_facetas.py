"""Tests del endpoint GET /audit/facetas (R87 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AuditLogRecord, UsuarioRecord


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
def usuario_coord(db_session):
    u = UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, usuario, rol, accion, tabla):
    db.add(AuditLogRecord(
        usuario_email=usuario, usuario_rol=rol,
        accion=accion, tabla=tabla, timestamp=ahora_utc(),
    ))
    db.commit()


class TestAuditFacetas:
    def test_vacio(self, client):
        r = client.get("/audit/facetas")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d == {"acciones": [], "tablas": [], "usuarios": [], "roles": []}

    def test_distinct_y_ordenado(self, client, db_session):
        _seed(db_session, "alice@x", "AUDITOR", "UPDATE", "glosas")
        _seed(db_session, "alice@x", "AUDITOR", "UPDATE", "glosas")  # duplicado
        _seed(db_session, "bob@x", "COORDINADOR", "DELETE", "usuarios")
        _seed(db_session, "carol@x", "AUDITOR", "CREATE", "glosas")

        r = client.get("/audit/facetas")
        d = r.json()
        # Cada valor aparece UNA vez y ordenado alfabéticamente
        assert d["acciones"] == ["CREATE", "DELETE", "UPDATE"]
        assert d["tablas"] == ["glosas", "usuarios"]
        assert d["usuarios"] == ["alice@x", "bob@x", "carol@x"]
        assert d["roles"] == ["AUDITOR", "COORDINADOR"]

    def test_excluye_nulos(self, client, db_session):
        _seed(db_session, "u@x", "AUDITOR", "X", "T")
        # Una entrada con campos nulos
        db_session.add(AuditLogRecord(
            usuario_email=None, usuario_rol=None,
            accion=None, tabla=None, timestamp=ahora_utc(),
        ))
        db_session.commit()

        r = client.get("/audit/facetas")
        d = r.json()
        # Solo el evento "real" aporta valores
        assert d["acciones"] == ["X"]
        assert d["tablas"] == ["T"]
        assert d["usuarios"] == ["u@x"]
        assert d["roles"] == ["AUDITOR"]
