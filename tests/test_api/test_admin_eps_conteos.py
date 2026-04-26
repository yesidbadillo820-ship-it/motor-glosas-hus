"""Tests del endpoint GET /admin/eps-conteos (R239 P1)."""
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


def _seed(db, eps, estado="RADICADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestAdminEPSConteos:
    def test_orden_y_counts(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "GRANDE")
        for _ in range(3):
            _seed(db_session, "GRANDE", estado="LEVANTADA")
        for _ in range(2):
            _seed(db_session, "PEQUENA")

        r = client.get("/admin/eps-conteos")
        d = r.json()
        # GRANDE tiene 8 (5 abiertas + 3 cerradas)
        assert d["items"][0]["eps"] == "GRANDE"
        assert d["items"][0]["count_total"] == 8
        assert d["items"][0]["count_abiertas"] == 5
        assert d["items"][1]["eps"] == "PEQUENA"
