"""Tests del endpoint GET /admin/inconsistencias-datos (R133 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestInconsistenciasDatos:
    def test_estructura(self, client):
        r = client.get("/admin/inconsistencias-datos")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_inconsistencias", "reglas_evaluadas", "items"):
            assert key in d
        # 5 reglas evaluadas
        assert d["reglas_evaluadas"] == 5

    def test_levantada_sin_recupero(self, client, db_session):
        _seed(db_session, estado="LEVANTADA", valor_recuperado=0)
        r = client.get("/admin/inconsistencias-datos")
        d = r.json()
        regla = next(it for it in d["items"]
                     if it["regla"] == "levantadas_sin_recupero")
        assert regla["count"] == 1

    def test_aceptada_con_recupero(self, client, db_session):
        _seed(db_session, estado="ACEPTADA", valor_recuperado=5000)
        r = client.get("/admin/inconsistencias-datos")
        d = r.json()
        regla = next(it for it in d["items"]
                     if it["regla"] == "aceptadas_con_recupero")
        assert regla["count"] == 1

    def test_decision_en_abierto(self, client, db_session):
        _seed(db_session,
              estado="RADICADA",
              fecha_decision_eps=ahora_utc())
        r = client.get("/admin/inconsistencias-datos")
        d = r.json()
        regla = next(it for it in d["items"]
                     if it["regla"] == "decision_eps_en_estado_abierto")
        assert regla["count"] == 1

    def test_glosa_correcta_no_aparece(self, client, db_session):
        # Glosa bien formada
        _seed(db_session, estado="LEVANTADA", valor_recuperado=10000)
        r = client.get("/admin/inconsistencias-datos")
        d = r.json()
        # Sin inconsistencias
        assert d["total_inconsistencias"] == 0

    def test_sample_ids_max_5(self, client, db_session):
        for _ in range(10):
            _seed(db_session, estado="LEVANTADA", valor_recuperado=0)
        r = client.get("/admin/inconsistencias-datos")
        d = r.json()
        regla = next(it for it in d["items"]
                     if it["regla"] == "levantadas_sin_recupero")
        assert regla["count"] == 10
        assert len(regla["sample_ids"]) == 5
