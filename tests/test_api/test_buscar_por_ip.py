"""Tests del endpoint GET /auditoria-forense/buscar-por-ip (R131 P1)."""
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


def _seed(db, ip, usuario, accion="UPDATE", min_atras=0):
    db.add(AuditLogRecord(
        usuario_email=usuario, accion=accion, tabla="glosas",
        ip=ip,
        timestamp=ahora_utc() - timedelta(minutes=min_atras),
    ))
    db.commit()


class TestBuscarPorIP:
    def test_ip_sin_eventos(self, client):
        r = client.get("/auditoria-forense/buscar-por-ip?ip=1.2.3.4")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_eventos"] == 0
        assert d["usuarios_distintos"] == []
        assert d["primer_evento_en"] is None

    def test_filtra_por_ip_estricto(self, client, db_session):
        _seed(db_session, "10.0.0.1", "alice@x")
        _seed(db_session, "10.0.0.1", "alice@x")
        _seed(db_session, "10.0.0.2", "bob@x")  # otra IP

        r = client.get("/auditoria-forense/buscar-por-ip?ip=10.0.0.1")
        d = r.json()
        assert d["total_eventos"] == 2
        assert d["usuarios_distintos"] == ["alice@x"]

    def test_multiples_usuarios_misma_ip(self, client, db_session):
        # Sospechoso: misma IP usada por múltiples usuarios
        _seed(db_session, "10.0.0.1", "alice@x")
        _seed(db_session, "10.0.0.1", "bob@x")
        _seed(db_session, "10.0.0.1", "carol@x")

        r = client.get("/auditoria-forense/buscar-por-ip?ip=10.0.0.1")
        d = r.json()
        assert d["usuarios_distintos"] == ["alice@x", "bob@x", "carol@x"]

    def test_acciones_distintas(self, client, db_session):
        _seed(db_session, "10.0.0.1", "u@x", accion="UPDATE")
        _seed(db_session, "10.0.0.1", "u@x", accion="DELETE")
        _seed(db_session, "10.0.0.1", "u@x", accion="UPDATE")

        r = client.get("/auditoria-forense/buscar-por-ip?ip=10.0.0.1")
        d = r.json()
        assert d["acciones_distintas"] == ["DELETE", "UPDATE"]

    def test_orden_desc_por_timestamp(self, client, db_session):
        _seed(db_session, "1.1.1.1", "u@x", min_atras=10)
        _seed(db_session, "1.1.1.1", "u@x", min_atras=2)
        _seed(db_session, "1.1.1.1", "u@x", min_atras=5)

        r = client.get("/auditoria-forense/buscar-por-ip?ip=1.1.1.1")
        d = r.json()
        timestamps = [it["timestamp"] for it in d["items"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_limit(self, client, db_session):
        for i in range(20):
            _seed(db_session, "1.1.1.1", "u@x", min_atras=i)
        r = client.get("/auditoria-forense/buscar-por-ip?ip=1.1.1.1&limit=5")
        d = r.json()
        assert len(d["items"]) == 5
