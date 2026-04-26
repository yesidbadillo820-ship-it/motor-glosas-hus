"""Tests del endpoint GET /admin/timeline-equipo (R126 P1)."""
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


def _seed_audit(db, usuario, accion="UPDATE", horas_atras=1):
    db.add(AuditLogRecord(
        usuario_email=usuario, accion=accion, tabla="glosas",
        timestamp=ahora_utc() - timedelta(hours=horas_atras),
    ))
    db.commit()


class TestTimelineEquipo:
    def test_vacio(self, client):
        r = client.get("/admin/timeline-equipo")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["serie"] == []

    def test_agrupa_por_hora(self, client, db_session):
        # 3 eventos hace 2 horas
        for _ in range(3):
            _seed_audit(db_session, "alice@x", horas_atras=2)
        # 1 evento hace 5 horas
        _seed_audit(db_session, "bob@x", horas_atras=5)

        r = client.get("/admin/timeline-equipo")
        d = r.json()
        # 2 horas distintas con actividad
        assert d["horas_con_actividad"] == 2
        # Suma total
        assert d["total_eventos"] == 4

    def test_por_usuario_y_acciones(self, client, db_session):
        for _ in range(5):
            _seed_audit(db_session, "alice@x", "UPDATE", horas_atras=2)
        for _ in range(2):
            _seed_audit(db_session, "bob@x", "DELETE", horas_atras=2)

        r = client.get("/admin/timeline-equipo")
        d = r.json()
        # Misma hora bucket
        bucket = d["serie"][0]
        assert bucket["por_usuario"]["alice@x"] == 5
        assert bucket["por_usuario"]["bob@x"] == 2
        # Acciones top
        acciones = {a["accion"]: a["n"] for a in bucket["acciones_top"]}
        assert acciones["UPDATE"] == 5
        assert acciones["DELETE"] == 2

    def test_orden_ascendente_por_hora(self, client, db_session):
        _seed_audit(db_session, "u@x", horas_atras=1)
        _seed_audit(db_session, "u@x", horas_atras=10)
        _seed_audit(db_session, "u@x", horas_atras=5)
        r = client.get("/admin/timeline-equipo")
        d = r.json()
        horas = [s["hora"] for s in d["serie"]]
        assert horas == sorted(horas)

    def test_excluye_fuera_de_ventana(self, client, db_session):
        _seed_audit(db_session, "u@x", horas_atras=1)   # dentro
        _seed_audit(db_session, "u@x", horas_atras=48)  # fuera (default 24h)
        r = client.get("/admin/timeline-equipo")
        d = r.json()
        assert d["total_eventos"] == 1
