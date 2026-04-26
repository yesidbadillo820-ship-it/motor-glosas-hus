"""Tests del endpoint GET /admin/glosas-creadas-hoy-detalle (R290 P1)."""
from __future__ import annotations

from datetime import timedelta

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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, dias_atras, valor):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestGlosasCreadasHoyDetalle:
    def test_solo_hoy(self, client, db_session):
        _seed(db_session, dias_atras=0, valor=1000)  # hoy
        _seed(db_session, dias_atras=2, valor=2000)  # ayer

        r = client.get("/admin/glosas-creadas-hoy-detalle")
        d = r.json()
        assert d["total_creadas"] == 1
        assert d["items"][0]["valor_objetado"] == 1000

    def test_orden_valor_desc(self, client, db_session):
        _seed(db_session, dias_atras=0, valor=100)
        _seed(db_session, dias_atras=0, valor=999)
        r = client.get("/admin/glosas-creadas-hoy-detalle")
        d = r.json()
        valores = [it["valor_objetado"] for it in d["items"]]
        assert valores == sorted(valores, reverse=True)
        assert d["valor_objetado_total"] == 1099

    def test_no_admin_403(self, db_session):
        from app.api.deps import get_usuario_actual
        from app.main import app
        no_admin = UsuarioRecord(
            id=99, email="x@x.com", rol="AUDITOR", activo=1,
        )
        app.dependency_overrides[get_db] = (
            lambda: iter([db_session]).__next__()
        )
        app.dependency_overrides[get_usuario_actual] = lambda: no_admin
        with TestClient(app) as c:
            r = c.get("/admin/glosas-creadas-hoy-detalle")
            assert r.status_code == 403
        app.dependency_overrides.clear()
