"""Tests del endpoint GET /admin/insight-financiero (R386 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
def admin():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, eps, obj, rec, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=obj, valor_recuperado=rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestInsightFinanciero:
    def test_top_y_bottom(self, client, db_session):
        # SAN: 100% rec
        for _ in range(3):
            _seed(db_session, "SAN", 1000, 1000)
        # MED: 50% rec
        for _ in range(3):
            _seed(db_session, "MED", 1000, 500)
        # NUEV: 25% rec
        for _ in range(3):
            _seed(db_session, "NUEV", 1000, 250)
        r = client.get("/admin/insight-financiero")
        d = r.json()
        assert d["top_3_eps_recuperacion"][0]["eps"] == "SAN"
        assert d["bottom_3_eps_recuperacion"][0]["eps"] == "NUEV"
        assert d["tasa_recuperacion_global_pct"] > 0

    def test_no_admin_403(self, db_session):
        from app.api.deps import get_usuario_actual
        from app.main import app
        no_admin = UsuarioRecord(
            id=99, email="x@x", rol="AUDITOR", activo=1,
        )
        app.dependency_overrides[get_db] = (
            lambda: iter([db_session]).__next__()
        )
        app.dependency_overrides[get_usuario_actual] = lambda: no_admin
        with TestClient(app) as c:
            r = c.get("/admin/insight-financiero")
            assert r.status_code == 403
        app.dependency_overrides.clear()
