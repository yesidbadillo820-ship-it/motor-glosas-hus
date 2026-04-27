"""Tests del endpoint GET /admin/digest-diario (R392 P1)."""
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


def _seed(db, dias=10, valor=1000, estado="RADICADA", gestor=None):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
    ))
    db.commit()


class TestDigestDiario:
    def test_estructura(self, client):
        r = client.get("/admin/digest-diario")
        d = r.json()
        for k in ("fecha_digest", "ayer", "hoy", "tendencia_creadas"):
            assert k in d

    def test_top_riesgo(self, client, db_session):
        # Glosa vencida y de alto valor
        _seed(db_session, dias=-5, valor=10_000_000)
        # Glosa vencida pero pequeña — no aparece
        _seed(db_session, dias=-5, valor=1000)
        r = client.get("/admin/digest-diario")
        d = r.json()
        assert len(d["top_riesgo_grandes_vencidas"]) == 1

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
            r = c.get("/admin/digest-diario")
            assert r.status_code == 403
        app.dependency_overrides.clear()
