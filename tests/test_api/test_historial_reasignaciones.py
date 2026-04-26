"""Tests del endpoint GET /admin/historial-reasignaciones (R156 P2)."""
from __future__ import annotations

from datetime import timedelta

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
def usuario_super(db_session):
    u = UsuarioRecord(
        id=1, email="root@hus.gov.co", rol="SUPER_ADMIN", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_super):
    from app.api.deps import get_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_admin] = lambda: usuario_super
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_audit(db, usuario, campo, anterior, nuevo, dias_atras=1):
    db.add(AuditLogRecord(
        usuario_email=usuario, accion="UPDATE",
        tabla="glosas", registro_id=1,
        campo=campo, valor_anterior=anterior, valor_nuevo=nuevo,
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestHistorialReasignaciones:
    def test_estructura(self, client):
        r = client.get("/admin/historial-reasignaciones")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "total_reasignaciones",
                    "top_5_quien_reasigna", "items"):
            assert key in d

    def test_filtra_solo_campos_relevantes(self, client, db_session):
        # Reasignación de gestor → debe aparecer
        _seed_audit(db_session, "u@x", "gestor_nombre", "Alice", "Bob")
        # Reasignación de auditor → debe aparecer
        _seed_audit(db_session, "u@x", "auditor_email",
                    "old@x", "new@x")
        # Cambio de otro campo → NO debe aparecer
        _seed_audit(db_session, "u@x", "valor_objetado", "1000", "2000")

        r = client.get("/admin/historial-reasignaciones")
        d = r.json()
        assert d["total_reasignaciones"] == 2

    def test_top_5_quien_reasigna(self, client, db_session):
        for _ in range(5):
            _seed_audit(db_session, "alice@x",
                        "gestor_nombre", "X", "Y")
        for _ in range(2):
            _seed_audit(db_session, "bob@x",
                        "gestor_nombre", "X", "Y")

        r = client.get("/admin/historial-reasignaciones")
        d = r.json()
        top = d["top_5_quien_reasigna"]
        assert top[0] == {"usuario": "alice@x", "reasignaciones": 5}
        assert top[1] == {"usuario": "bob@x", "reasignaciones": 2}

    def test_items_incluyen_de_quien_a_quien(self, client, db_session):
        _seed_audit(db_session, "u@x", "gestor_nombre", "Alice", "Bob")
        r = client.get("/admin/historial-reasignaciones")
        d = r.json()
        item = d["items"][0]
        assert item["anterior"] == "Alice"
        assert item["nuevo"] == "Bob"
        assert item["campo"] == "gestor_nombre"

    def test_excluye_fuera_de_ventana(self, client, db_session):
        _seed_audit(db_session, "u@x", "gestor_nombre", "A", "B",
                    dias_atras=5)
        _seed_audit(db_session, "u@x", "gestor_nombre", "A", "B",
                    dias_atras=60)
        r = client.get("/admin/historial-reasignaciones?dias=30")
        d = r.json()
        assert d["total_reasignaciones"] == 1
