"""Tests del endpoint GET /glosas/stats/dictamen-vs-tasa-exito (R224 P1)."""
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


def _seed(db, dictamen, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dictamen=dictamen,
    ))
    db.commit()


class TestDictamenVsTasaExito:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/dictamen-vs-tasa-exito")
        d = r.json()
        # 4 bandas
        assert len(d["items"]) == 4

    def test_largo_levanta_mas(self, client, db_session):
        # LARGO: 3 LEV / 4 → 75%
        for _ in range(3):
            _seed(db_session, "x" * 3000, estado="LEVANTADA")
        _seed(db_session, "x" * 3000, estado="ACEPTADA")
        # CORTO: 0 LEV / 1 → 0%
        _seed(db_session, "x" * 200, estado="ACEPTADA")

        r = client.get("/glosas/stats/dictamen-vs-tasa-exito")
        d = r.json()
        items = {it["banda"]: it for it in d["items"]}
        assert items["LARGO_>=2000"]["tasa_levantamiento_pct"] == 75.0
        assert items["CORTO_100a499"]["tasa_levantamiento_pct"] == 0.0
