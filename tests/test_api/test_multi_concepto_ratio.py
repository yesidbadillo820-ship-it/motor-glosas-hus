"""Tests del endpoint GET /glosas/stats/multi-concepto-ratio (R213 P1)."""
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


def _seed_glosa(db, gid):
    db.add(GlosaRecord(
        id=gid, eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_concepto(db, gid):
    db.add(ConceptoGlosaRecord(
        glosa_id=gid, codigo_glosa="C", valor_objetado=100,
    ))
    db.commit()


class TestMultiConceptoRatio:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/multi-concepto-ratio")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_glosas", "glosas_con_conceptos",
                    "glosas_multi_concepto", "glosas_simples",
                    "ratio_multi_pct",
                    "promedio_conceptos_por_glosa"):
            assert key in d

    def test_ratio_calculado(self, client, db_session):
        # Glosa 1: 3 conceptos (multi)
        _seed_glosa(db_session, 1)
        for _ in range(3):
            _seed_concepto(db_session, 1)
        # Glosa 2: 1 concepto (simple)
        _seed_glosa(db_session, 2)
        _seed_concepto(db_session, 2)
        # Glosa 3: 1 concepto (simple)
        _seed_glosa(db_session, 3)
        _seed_concepto(db_session, 3)

        r = client.get("/glosas/stats/multi-concepto-ratio")
        d = r.json()
        # 1 multi de 3 con conceptos = 33.33%
        assert d["glosas_con_conceptos"] == 3
        assert d["glosas_multi_concepto"] == 1
        assert d["glosas_simples"] == 2
        assert d["ratio_multi_pct"] == 33.33
        # Promedio = (3+1+1)/3 = 1.67
        assert d["promedio_conceptos_por_glosa"] == 1.67
