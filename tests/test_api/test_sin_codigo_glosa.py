"""Tests del endpoint GET /glosas/sin-codigo-glosa (R209 P1)."""
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
def usuario():
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, codigo, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestSinCodigoGlosa:
    def test_estructura(self, client):
        r = client.get("/glosas/sin-codigo-glosa")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_sin_codigo", "items"):
            assert key in d

    def test_detecta_null_y_vacio(self, client, db_session):
        _seed(db_session, codigo=None)
        _seed(db_session, codigo="")
        _seed(db_session, codigo="TA0201")  # con código

        r = client.get("/glosas/sin-codigo-glosa")
        d = r.json()
        assert d["total_sin_codigo"] == 2

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, codigo=None, estado="LEVANTADA")
        r = client.get("/glosas/sin-codigo-glosa")
        d = r.json()
        assert d["items"] == []
