"""Tests del endpoint GET /glosas/stats/dictamen-calidad-distribucion (R222 P1)."""
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


def _seed(db, dictamen):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        dictamen=dictamen,
    ))
    db.commit()


class TestDictamenCalidadDistribucion:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/dictamen-calidad-distribucion")
        d = r.json()
        # 5 bandas siempre
        assert len(d["items"]) == 5

    def test_clasificacion(self, client, db_session):
        _seed(db_session, None)         # SIN_DICTAMEN
        _seed(db_session, "x" * 50)     # MUY_CORTO
        _seed(db_session, "x" * 300)    # CORTO
        _seed(db_session, "x" * 1500)   # MEDIO
        _seed(db_session, "x" * 3000)   # LARGO

        r = client.get("/glosas/stats/dictamen-calidad-distribucion")
        d = r.json()
        items = {it["banda"]: it for it in d["items"]}
        assert items["SIN_DICTAMEN"]["count"] == 1
        assert items["MUY_CORTO"]["count"] == 1
        assert items["CORTO"]["count"] == 1
        assert items["MEDIO"]["count"] == 1
        assert items["LARGO"]["count"] == 1
