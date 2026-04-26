"""Tests del endpoint GET /auditoria-forense/ips-frecuentes (R131 P2)."""
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


def _seed(db, ip, usuario, dias_atras=1):
    db.add(AuditLogRecord(
        usuario_email=usuario, accion="X", tabla="T",
        ip=ip,
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestIpsFrecuentes:
    def test_vacio(self, client):
        r = client.get("/auditoria-forense/ips-frecuentes")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_orden_por_eventos_desc(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "10.0.0.1", "u@x")
        for _ in range(2):
            _seed(db_session, "10.0.0.2", "u@x")
        _seed(db_session, "10.0.0.3", "u@x")

        r = client.get("/auditoria-forense/ips-frecuentes")
        d = r.json()
        ips = [it["ip"] for it in d["items"]]
        assert ips == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
        assert d["items"][0]["eventos"] == 5

    def test_usuarios_distintos_count(self, client, db_session):
        # 1 IP con 3 usuarios distintos
        _seed(db_session, "1.1.1.1", "alice@x")
        _seed(db_session, "1.1.1.1", "bob@x")
        _seed(db_session, "1.1.1.1", "carol@x")

        r = client.get("/auditoria-forense/ips-frecuentes")
        d = r.json()
        assert d["items"][0]["usuarios_distintos"] == 3

    def test_excluye_ip_null(self, client, db_session):
        # Evento sin IP NO debe aparecer
        db_session.add(AuditLogRecord(
            usuario_email="u@x", accion="X", tabla="T",
            ip=None, timestamp=ahora_utc(),
        ))
        db_session.commit()

        r = client.get("/auditoria-forense/ips-frecuentes")
        d = r.json()
        assert d["items"] == []

    def test_excluye_fuera_de_ventana(self, client, db_session):
        _seed(db_session, "1.1.1.1", "u@x", dias_atras=5)
        _seed(db_session, "1.1.1.1", "u@x", dias_atras=60)
        r = client.get("/auditoria-forense/ips-frecuentes?dias=30")
        d = r.json()
        # Solo el de 5d cuenta
        assert d["items"][0]["eventos"] == 1

    def test_top_limita(self, client, db_session):
        for i in range(10):
            _seed(db_session, f"10.0.0.{i}", "u@x")
        r = client.get("/auditoria-forense/ips-frecuentes?top=3")
        d = r.json()
        assert len(d["items"]) == 3
        assert d["total_ips_unicas"] == 10
