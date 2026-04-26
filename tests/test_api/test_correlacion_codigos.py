"""Tests del endpoint GET /glosas/stats/correlacion-codigos (R108 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ConceptoGlosaRecord, GlosaRecord, UsuarioRecord,
)


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


def _seed_glosa_y_conceptos(db, factura, codigos):
    g = GlosaRecord(
        eps="X", paciente="X", codigo_glosa=codigos[0],
        valor_objetado=1000, etapa="X", estado="RADICADA",
        factura=factura, creado_en=ahora_utc(),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    for cod in codigos:
        db.add(ConceptoGlosaRecord(
            glosa_id=g.id, factura=factura, codigo_glosa=cod,
        ))
    db.commit()


class TestCorrelacionCodigos:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/correlacion-codigos")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_factura_un_solo_codigo_no_genera_par(self, client, db_session):
        _seed_glosa_y_conceptos(db_session, "F-1", ["TA0201"])
        r = client.get("/glosas/stats/correlacion-codigos")
        d = r.json()
        assert d["items"] == []

    def test_par_simple(self, client, db_session):
        # Factura F-1 tiene TA0201 + FA0603
        _seed_glosa_y_conceptos(db_session, "F-1", ["TA0201", "FA0603"])
        r = client.get("/glosas/stats/correlacion-codigos")
        d = r.json()
        assert d["items"][0]["codigo_a"] == "FA0603"  # ordenados alfabéticamente
        assert d["items"][0]["codigo_b"] == "TA0201"
        assert d["items"][0]["co_frecuencia"] == 1

    def test_co_frecuencia_acumula(self, client, db_session):
        # 3 facturas con el mismo par
        for f in ["F-1", "F-2", "F-3"]:
            _seed_glosa_y_conceptos(db_session, f, ["TA0201", "FA0603"])
        r = client.get("/glosas/stats/correlacion-codigos")
        d = r.json()
        assert d["items"][0]["co_frecuencia"] == 3

    def test_orden_desc_por_co_frecuencia(self, client, db_session):
        # Par A,B aparece 5 veces
        for i in range(5):
            _seed_glosa_y_conceptos(db_session, f"F-AB-{i}", ["A", "B"])
        # Par C,D aparece 2 veces
        for i in range(2):
            _seed_glosa_y_conceptos(db_session, f"F-CD-{i}", ["C", "D"])
        r = client.get("/glosas/stats/correlacion-codigos")
        d = r.json()
        # AB primero
        assert d["items"][0]["codigo_a"] == "A"
        assert d["items"][0]["co_frecuencia"] == 5
        assert d["items"][1]["codigo_a"] == "C"
        assert d["items"][1]["co_frecuencia"] == 2

    def test_top_limita(self, client, db_session):
        # Generar 5 pares distintos
        for c in ["X", "Y", "Z", "W", "V"]:
            _seed_glosa_y_conceptos(db_session, f"F-{c}", ["A", c])
        r = client.get("/glosas/stats/correlacion-codigos?top=2")
        d = r.json()
        assert len(d["items"]) == 2
