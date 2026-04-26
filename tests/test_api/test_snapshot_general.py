"""Tests del endpoint GET /sistema/snapshot-general (R158 P2)."""
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
def usuario_coord():
    return UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestSnapshotGeneral:
    def test_estructura(self, client):
        r = client.get("/sistema/snapshot-general")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("evaluado_en", "counts"):
            assert key in d
        for tabla in ("glosas", "usuarios", "audit_log", "ai_calls",
                      "ai_cache", "dictamen_versiones",
                      "conciliaciones", "contratos", "plantillas",
                      "plantillas_gold", "papelera"):
            assert tabla in d["counts"]

    def test_counts_son_int(self, client):
        r = client.get("/sistema/snapshot-general")
        d = r.json()
        for valor in d["counts"].values():
            assert isinstance(valor, int)

    def test_counts_actualizados(self, client, db_session):
        for _ in range(5):
            db_session.add(GlosaRecord(
                eps="X", paciente="X", codigo_glosa="C",
                valor_objetado=1000, etapa="X", estado="RADICADA",
                creado_en=ahora_utc(),
            ))
        db_session.commit()
        r = client.get("/sistema/snapshot-general")
        d = r.json()
        assert d["counts"]["glosas"] == 5
