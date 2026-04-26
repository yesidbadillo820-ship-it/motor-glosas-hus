"""Tests del endpoint GET /usuarios/yo/menciones-pendientes (R216 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import ComentarioGlosaRecord, UsuarioRecord


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
    return UsuarioRecord(
        id=1, email="alice@hus.com", rol="AUDITOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, mencion, resuelto=0, autor="bob@x"):
    db.add(ComentarioGlosaRecord(
        glosa_id=1, autor_email=autor,
        texto="x", mencion=mencion, resuelto=resuelto,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestMencionesPendientes:
    def test_estructura(self, client):
        r = client.get("/usuarios/yo/menciones-pendientes")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("usuario_email", "total_pendientes", "items"):
            assert key in d

    def test_filtra_por_email(self, client, db_session):
        _seed(db_session, mencion="alice@hus.com")
        _seed(db_session, mencion="bob@x")  # no es alice

        r = client.get("/usuarios/yo/menciones-pendientes")
        d = r.json()
        assert d["total_pendientes"] == 1

    def test_excluye_resueltas(self, client, db_session):
        _seed(db_session, mencion="alice@hus.com", resuelto=0)
        _seed(db_session, mencion="alice@hus.com", resuelto=1)

        r = client.get("/usuarios/yo/menciones-pendientes")
        d = r.json()
        assert d["total_pendientes"] == 1
