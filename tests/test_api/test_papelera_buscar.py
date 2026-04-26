"""Tests del endpoint GET /papelera/buscar (R171 P1)."""
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
from app.models.db import GlosaEliminadaRecord, UsuarioRecord


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
def usuario_coord(db_session):
    u = UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gid_orig, usuario):
    db.add(GlosaEliminadaRecord(
        glosa_id_original=gid_orig, snapshot_json="{}",
        eliminado_por=usuario,
        eliminado_en=ahora_utc(),
    ))
    db.commit()


class TestPapeleraBuscar:
    def test_estructura(self, client):
        r = client.get("/papelera/buscar")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("filtro_glosa_id_original",
                    "filtro_eliminado_por", "total", "items"):
            assert key in d

    def test_filtra_por_glosa_id(self, client, db_session):
        _seed(db_session, 123, "u@x")
        _seed(db_session, 456, "u@x")
        r = client.get("/papelera/buscar?glosa_id_original=123")
        d = r.json()
        assert d["total"] == 1
        assert d["items"][0]["glosa_id_original"] == 123

    def test_filtra_por_usuario(self, client, db_session):
        _seed(db_session, 1, "alice@x")
        _seed(db_session, 2, "bob@x")
        r = client.get("/papelera/buscar?eliminado_por=alice@x")
        d = r.json()
        assert d["total"] == 1
        assert d["items"][0]["eliminado_por"] == "alice@x"

    def test_combina_filtros(self, client, db_session):
        _seed(db_session, 1, "alice@x")
        _seed(db_session, 1, "bob@x")
        _seed(db_session, 2, "alice@x")

        r = client.get(
            "/papelera/buscar?glosa_id_original=1&eliminado_por=alice@x"
        )
        d = r.json()
        assert d["total"] == 1
