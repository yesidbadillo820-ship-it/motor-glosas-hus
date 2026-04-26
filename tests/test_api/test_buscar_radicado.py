"""Tests del endpoint GET /glosas/buscar-radicado (R152 P2)."""
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


def _seed(db, radicado, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(numero_radicado=radicado, **base))
    db.commit()


class TestBuscarRadicado:
    def test_radicado_inexistente(self, client):
        r = client.get("/glosas/buscar-radicado?radicado=NO_EXISTE")
        d = r.json()
        assert d["encontradas"] == 0
        assert d["items"] == []

    def test_match_exacto(self, client, db_session):
        _seed(db_session, "RAD-001", eps="SANITAS")
        _seed(db_session, "RAD-002", eps="OTRA")
        r = client.get("/glosas/buscar-radicado?radicado=RAD-001")
        d = r.json()
        assert d["encontradas"] == 1
        assert d["items"][0]["eps"] == "SANITAS"

    def test_es_exact_match(self, client, db_session):
        # Búsqueda con sub-string NO debe matchear
        _seed(db_session, "RAD-12345")
        r = client.get("/glosas/buscar-radicado?radicado=12345")
        d = r.json()
        # Exact match: no encuentra parcial
        assert d["encontradas"] == 0

    def test_multiples_glosas_mismo_radicado(self, client, db_session):
        # Caso raro pero posible
        _seed(db_session, "DUPLICADO")
        _seed(db_session, "DUPLICADO")
        r = client.get("/glosas/buscar-radicado?radicado=DUPLICADO")
        d = r.json()
        assert d["encontradas"] == 2
