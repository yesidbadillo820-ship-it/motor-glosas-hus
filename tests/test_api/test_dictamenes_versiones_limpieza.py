"""Tests del endpoint GET /admin/dictamenes-versiones-limpieza (R205 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import DictamenVersionRecord, UsuarioRecord


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


def _seed(db, glosa_id):
    db.add(DictamenVersionRecord(
        glosa_id=glosa_id, dictamen_html="<p>X</p>",
        accion="REFINAR", creado_en=ahora_utc(),
    ))
    db.commit()


class TestDictamenesVersionesLimpieza:
    def test_estructura(self, client):
        r = client.get("/admin/dictamenes-versiones-limpieza")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("max_versiones_por_glosa",
                    "glosas_que_exceden_max",
                    "filas_excedentes",
                    "bytes_estimados_recuperables",
                    "mb_estimados_recuperables"):
            assert key in d

    def test_glosa_con_15_versiones_excede(self, client, db_session):
        # Glosa 1 con 15 versiones, max=10 → excedente=5
        for _ in range(15):
            _seed(db_session, 1)
        # Glosa 2 con 5 versiones (no excede)
        for _ in range(5):
            _seed(db_session, 2)

        r = client.get(
            "/admin/dictamenes-versiones-limpieza"
            "?max_versiones_por_glosa=10"
        )
        d = r.json()
        assert d["glosas_que_exceden_max"] == 1
        assert d["filas_excedentes"] == 5

    def test_max_alto_no_excede(self, client, db_session):
        for _ in range(15):
            _seed(db_session, 1)
        r = client.get(
            "/admin/dictamenes-versiones-limpieza"
            "?max_versiones_por_glosa=100"
        )
        d = r.json()
        assert d["glosas_que_exceden_max"] == 0
