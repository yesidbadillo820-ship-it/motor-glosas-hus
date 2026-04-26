"""Tests del endpoint GET /glosas/stats/proceso-bilateral (R197 P1)."""
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


def _seed(db, estado, valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestProcesoBilateral:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/proceso-bilateral")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_glosas", "pipeline"):
            assert key in d
        # 8 estados oficiales siempre presentes
        assert len(d["pipeline"]) == 8

    def test_pipeline_estados_oficiales(self, client):
        r = client.get("/glosas/stats/proceso-bilateral")
        d = r.json()
        estados = [it["estado"] for it in d["pipeline"]]
        for e in ("RADICADA", "RESPONDIDA", "RATIFICADA",
                  "CONCILIADA", "LEVANTADA", "ACEPTADA",
                  "ARCHIVADA", "EXTEMPORANEA"):
            assert e in estados

    def test_counts_correctos(self, client, db_session):
        _seed(db_session, "RADICADA", valor=10_000)
        _seed(db_session, "RADICADA", valor=20_000)
        _seed(db_session, "LEVANTADA", valor=5_000)

        r = client.get("/glosas/stats/proceso-bilateral")
        d = r.json()
        items = {it["estado"]: it for it in d["pipeline"]}
        assert items["RADICADA"]["count"] == 2
        assert items["RADICADA"]["valor"] == 30_000
        assert items["LEVANTADA"]["count"] == 1
