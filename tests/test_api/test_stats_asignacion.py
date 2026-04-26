"""Tests del endpoint GET /admin/stats-asignacion (R184 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord


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


def _seed(db, gestor=None, auditor=None):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        gestor_nombre=gestor, auditor_email=auditor,
    ))
    db.commit()


class TestStatsAsignacion:
    def test_estructura(self, client):
        r = client.get("/admin/stats-asignacion")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_abiertas", "con_gestor", "con_auditor",
                    "sin_nadie", "gestores_distintos",
                    "carga_min_por_gestor",
                    "carga_max_por_gestor",
                    "carga_mediana_por_gestor"):
            assert key in d

    def test_counts(self, client, db_session):
        _seed(db_session, gestor="Alice")
        _seed(db_session, auditor="bob@x")
        _seed(db_session)  # sin nadie

        r = client.get("/admin/stats-asignacion")
        d = r.json()
        assert d["total_abiertas"] == 3
        assert d["con_gestor"] == 1
        assert d["con_auditor"] == 1
        assert d["sin_nadie"] == 1

    def test_carga_imbalance(self, client, db_session):
        # Alice: 5 glosas, Bob: 1
        for _ in range(5):
            _seed(db_session, gestor="Alice")
        _seed(db_session, gestor="Bob")

        r = client.get("/admin/stats-asignacion")
        d = r.json()
        assert d["gestores_distintos"] == 2
        assert d["carga_max_por_gestor"] == 5
        assert d["carga_min_por_gestor"] == 1
