"""Tests del endpoint GET /admin/glosas-sin-codigo-respuesta (R278 P1)."""
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


def _seed(db, codigo_resp=None, estado="LEVANTADA", valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        codigo_respuesta=codigo_resp,
    ))
    db.commit()


class TestGlosasSinCodigoRespuesta:
    def test_decididas_sin_codigo(self, client, db_session):
        _seed(db_session, codigo_resp=None, estado="LEVANTADA")
        _seed(db_session, codigo_resp="", estado="RATIFICADA")
        _seed(db_session, codigo_resp="RE9501", estado="LEVANTADA")
        # Solo las primeras 2 deberían contar
        r = client.get("/admin/glosas-sin-codigo-respuesta")
        d = r.json()
        assert d["total_sin_codigo_respuesta"] == 2

    def test_excluye_no_decididas(self, client, db_session):
        _seed(db_session, codigo_resp=None, estado="RADICADA")
        r = client.get("/admin/glosas-sin-codigo-respuesta")
        d = r.json()
        assert d["total_sin_codigo_respuesta"] == 0

    def test_orden_desc(self, client, db_session):
        _seed(db_session, valor=100, estado="LEVANTADA")
        _seed(db_session, valor=999, estado="LEVANTADA")
        r = client.get("/admin/glosas-sin-codigo-respuesta")
        d = r.json()
        valores = [it["valor_objetado"] for it in d["items"]]
        assert valores == sorted(valores, reverse=True)
