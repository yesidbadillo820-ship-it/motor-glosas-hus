"""Tests del endpoint GET /glosas/stats/codigos-mas-recuperados (R244 P1)."""
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


def _seed(db, codigo, valor_rec):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa=codigo,
        valor_objetado=10000, valor_recuperado=valor_rec,
        etapa="X", estado="LEVANTADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestCodigosMasRecuperados:
    def test_orden_desc(self, client, db_session):
        _seed(db_session, "GANADOR", 10_000)
        _seed(db_session, "GANADOR", 20_000)
        _seed(db_session, "MENOR", 5_000)

        r = client.get("/glosas/stats/codigos-mas-recuperados")
        d = r.json()
        assert d["items"][0]["codigo_glosa"] == "GANADOR"
        assert d["items"][0]["valor_recuperado_total"] == 30_000
        assert d["items"][1]["codigo_glosa"] == "MENOR"

    def test_excluye_sin_recuperacion(self, client, db_session):
        _seed(db_session, "X", 0)
        r = client.get("/glosas/stats/codigos-mas-recuperados")
        d = r.json()
        assert d["items"] == []
