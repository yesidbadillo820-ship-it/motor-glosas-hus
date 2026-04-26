"""Tests del endpoint GET /glosas/stats/codigos-respuesta-distribucion (R238 P1)."""
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


def _seed(db, codigo_respuesta):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        codigo_respuesta=codigo_respuesta,
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestCodigosRespuestaDistribucion:
    def test_distribucion(self, client, db_session):
        for _ in range(6):
            _seed(db_session, "RE9901")
        for _ in range(2):
            _seed(db_session, "RE9502")
        _seed(db_session, "RE9801")
        # Total = 9 → RE9901 66.67%, RE9502 22.22%

        r = client.get("/glosas/stats/codigos-respuesta-distribucion")
        d = r.json()
        items = {it["codigo_respuesta"]: it for it in d["items"]}
        assert items["RE9901"]["count"] == 6
        assert items["RE9502"]["count"] == 2
        assert items["RE9801"]["count"] == 1

    def test_excluye_null(self, client, db_session):
        _seed(db_session, None)
        r = client.get("/glosas/stats/codigos-respuesta-distribucion")
        d = r.json()
        assert d["items"] == []
