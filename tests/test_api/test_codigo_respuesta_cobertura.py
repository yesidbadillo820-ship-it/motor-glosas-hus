"""Tests del endpoint GET /admin/codigo-respuesta-cobertura (R343 P1)."""
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


def _seed(db, eps, codigo_glosa, codigo_respuesta):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo_glosa,
        valor_objetado=1000, etapa="X", estado="LEVANTADA",
        creado_en=ahora_utc(),
        codigo_respuesta=codigo_respuesta,
    ))
    db.commit()


class TestCodigoRespuestaCobertura:
    def test_cobertura(self, client, db_session):
        _seed(db_session, "SANITAS", "TA01", "RE9501")
        _seed(db_session, "EPS001", "TA01", "RE9501")
        _seed(db_session, "OTRA", "FA06", "RE9701")

        r = client.get("/admin/codigo-respuesta-cobertura")
        d = r.json()
        b = {it["codigo_respuesta"]: it for it in d["items"]}
        assert b["RE9501"]["count_total"] == 2
        assert b["RE9501"]["eps_distintas"] == 2
        assert b["RE9501"]["codigos_glosa_distintos"] == 1
        assert b["RE9701"]["eps_distintas"] == 1
