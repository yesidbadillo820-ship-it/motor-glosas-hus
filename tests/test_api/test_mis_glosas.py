"""Tests del endpoint GET /usuarios/yo/mis-glosas (R130 P2)."""
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
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice", rol="AUDITOR", activo=1,
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestMisGlosas:
    def test_estructura_paginacion(self, client):
        r = client.get("/usuarios/yo/mis-glosas")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("items", "total", "page", "per_page", "pages"):
            assert key in d

    def test_solo_mis_glosas(self, client, db_session):
        _seed(db_session, gestor_nombre="Alice")
        _seed(db_session, auditor_email="alice@hus.com")
        _seed(db_session, gestor_nombre="Bob")  # no
        r = client.get("/usuarios/yo/mis-glosas")
        d = r.json()
        assert d["total"] == 2

    def test_filtro_por_estado(self, client, db_session):
        _seed(db_session, gestor_nombre="Alice", estado="RADICADA")
        _seed(db_session, gestor_nombre="Alice", estado="LEVANTADA")
        _seed(db_session, gestor_nombre="Alice", estado="LEVANTADA")
        r = client.get("/usuarios/yo/mis-glosas?estado=LEVANTADA")
        d = r.json()
        assert d["total"] == 2
        assert all(it["estado"] == "LEVANTADA" for it in d["items"])

    def test_paginacion(self, client, db_session):
        for _ in range(30):
            _seed(db_session, gestor_nombre="Alice")
        r = client.get("/usuarios/yo/mis-glosas?page=1&per_page=10")
        d = r.json()
        assert d["total"] == 30
        assert d["page"] == 1
        assert d["per_page"] == 10
        assert d["pages"] == 3
        assert len(d["items"]) == 10

        r2 = client.get("/usuarios/yo/mis-glosas?page=3&per_page=10")
        d2 = r2.json()
        assert len(d2["items"]) == 10

    def test_per_page_cap_100(self, client, db_session):
        # Pedir 999 → cap a 100
        r = client.get("/usuarios/yo/mis-glosas?per_page=999")
        d = r.json()
        assert d["per_page"] == 100
