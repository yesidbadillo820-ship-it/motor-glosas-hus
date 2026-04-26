"""Tests del endpoint GET /admin/conciliaciones-vencidas (R206 P1)."""
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
from app.models.db import ConciliacionRecord, UsuarioRecord


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


def _seed(db, dias_atras_audiencia, estado="PROGRAMADA"):
    db.add(ConciliacionRecord(
        glosa_id=1,
        fecha_audiencia=ahora_utc() - timedelta(days=dias_atras_audiencia),
        estado_bilateral=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestConciliacionesVencidas:
    def test_estructura(self, client):
        r = client.get("/admin/conciliaciones-vencidas")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_atrasadas", "items"):
            assert key in d

    def test_detecta_atrasadas(self, client, db_session):
        # Atrasada (5d en el pasado, sin acta)
        _seed(db_session, 5, "PROGRAMADA")
        # Atrasada (10d, EPS_RESPONDIO)
        _seed(db_session, 10, "EPS_RESPONDIO")
        # NO atrasada: con acta firmada
        _seed(db_session, 5, "ACTA_FIRMADA")
        # NO atrasada: futura
        _seed(db_session, -10, "PROGRAMADA")

        r = client.get("/admin/conciliaciones-vencidas")
        d = r.json()
        assert d["total_atrasadas"] == 2

    def test_orden_desc_dias_atraso(self, client, db_session):
        _seed(db_session, 5, "PROGRAMADA")
        _seed(db_session, 30, "PROGRAMADA")
        _seed(db_session, 15, "PROGRAMADA")

        r = client.get("/admin/conciliaciones-vencidas")
        d = r.json()
        atrasos = [it["dias_atraso"] for it in d["items"]]
        assert atrasos == sorted(atrasos, reverse=True)
