"""Tests del endpoint GET /glosas/stats/calidad-dictamen-por-gestor (R261 P1)."""
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


def _seed(db, gestor, dictamen):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dictamen=dictamen,
    ))
    db.commit()


class TestCalidadDictamen:
    def test_corto_vs_largo(self, client, db_session):
        # Alice: 1 corto
        _seed(db_session, "Alice", "no")
        # Bob: 1 largo
        _seed(db_session, "Bob", "x" * 250)

        r = client.get(
            "/glosas/stats/calidad-dictamen-por-gestor?min_glosas=1"
        )
        d = r.json()
        bob = next(x for x in d["items"] if x["gestor"] == "Bob")
        alice = next(x for x in d["items"] if x["gestor"] == "Alice")
        assert bob["count_largos"] == 1
        assert bob["count_cortos"] == 0
        assert alice["count_cortos"] == 1
        assert alice["pct_completos"] == 0.0
        assert bob["pct_completos"] == 100.0
        # Ordenado DESC por len_promedio
        assert d["items"][0]["gestor"] == "Bob"

    def test_min_glosas_filter(self, client, db_session):
        _seed(db_session, "Solo", "x" * 100)
        r = client.get(
            "/glosas/stats/calidad-dictamen-por-gestor?min_glosas=5"
        )
        d = r.json()
        assert d["items"] == []
