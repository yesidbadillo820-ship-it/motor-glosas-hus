"""Tests del endpoint GET /usuarios/yo/worklist (R123 P1)."""
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


class TestWorklistPersonal:
    def test_vacio(self, client):
        r = client.get("/usuarios/yo/worklist")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["usuario_email"] == "alice@hus.com"
        assert d["items"] == []

    def test_solo_asignadas_a_usuario(self, client, db_session):
        # Asignada a Alice (gestor_nombre)
        _seed(db_session, gestor_nombre="Alice")
        # Asignada a Alice (auditor_email)
        _seed(db_session, auditor_email="alice@hus.com")
        # NO asignada
        _seed(db_session, gestor_nombre="Bob")

        r = client.get("/usuarios/yo/worklist")
        d = r.json()
        assert d["total_asignadas"] == 2

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, gestor_nombre="Alice", estado="LEVANTADA")
        _seed(db_session, gestor_nombre="Alice", estado="ACEPTADA")
        r = client.get("/usuarios/yo/worklist")
        d = r.json()
        assert d["items"] == []

    def test_orden_por_score_desc(self, client, db_session):
        # Alice 1: vencida (+100)
        _seed(db_session, gestor_nombre="Alice", dias_restantes=-5)
        # Alice 2: solo crítica (+50)
        _seed(db_session, gestor_nombre="Alice", dias_restantes=2)
        r = client.get("/usuarios/yo/worklist")
        d = r.json()
        scores = [it["score"] for it in d["items"]]
        assert scores == sorted(scores, reverse=True)
        assert d["items"][0]["score"] >= 100

    def test_limit_respetado(self, client, db_session):
        for _ in range(15):
            _seed(db_session, gestor_nombre="Alice", dias_restantes=2)
        r = client.get("/usuarios/yo/worklist?limit=5")
        d = r.json()
        assert len(d["items"]) == 5
        assert d["total_asignadas"] == 15
