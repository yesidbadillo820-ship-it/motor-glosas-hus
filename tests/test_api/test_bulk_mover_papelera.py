"""Tests del endpoint /glosas/bulk-mover-papelera (R71 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaEliminadaRecord, GlosaRecord, UsuarioRecord


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
def usuario_coordinador():
    return UsuarioRecord(id=1, email="coord@hus.com", rol="COORDINADOR", activo=1)


def _seed_n(db, n):
    ids = []
    for i in range(n):
        g = GlosaRecord(
            eps="X", paciente=f"P{i}", codigo_glosa="TA0201",
            valor_objetado=100, etapa="X", estado="RADICADA",
            creado_en=ahora_utc(),
        )
        db.add(g)
        db.commit()
        db.refresh(g)
        ids.append(g.id)
    return ids


@pytest.fixture
def client(db_session, usuario_coordinador):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coordinador
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestBulkMoverPapelera:
    def test_dry_run_no_borra(self, client, db_session):
        ids = _seed_n(db_session, 3)
        r = client.post("/glosas/bulk-mover-papelera", json={
            "glosa_ids": ids, "dry_run": True,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["dry_run"] is True
        assert d["movidas_a_papelera"] == 3
        # NO se borraron de BD
        assert db_session.query(GlosaRecord).count() == 3
        assert db_session.query(GlosaEliminadaRecord).count() == 0

    def test_real_mueve_a_papelera(self, client, db_session):
        ids = _seed_n(db_session, 2)
        r = client.post("/glosas/bulk-mover-papelera", json={
            "glosa_ids": ids,
            "motivo": "Importadas por error",
        })
        d = r.json()
        assert d["movidas_a_papelera"] == 2
        # historial vacío, papelera con 2
        assert db_session.query(GlosaRecord).count() == 0
        assert db_session.query(GlosaEliminadaRecord).count() == 2

    def test_no_encontradas_no_rompen_batch(self, client, db_session):
        ids = _seed_n(db_session, 2)
        r = client.post("/glosas/bulk-mover-papelera", json={
            "glosa_ids": ids + [99999],
        })
        d = r.json()
        assert d["movidas_a_papelera"] == 2
        assert d["no_encontradas"] == [99999]

    def test_lista_vacia_falla(self, client):
        r = client.post("/glosas/bulk-mover-papelera", json={
            "glosa_ids": [],
        })
        assert r.status_code == 422

    def test_cap_200(self, client):
        r = client.post("/glosas/bulk-mover-papelera", json={
            "glosa_ids": list(range(1, 202)),
        })
        assert r.status_code == 422
