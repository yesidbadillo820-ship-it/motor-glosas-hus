"""Tests del endpoint GET /glosas/stats/factura-tasa-cierre (R354 P1)."""
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


def _seed(db, factura, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C", factura=factura,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestFacturaTasaCierre:
    def test_calcula(self, client, db_session):
        # F1: 3 total, 1 cerrada → 33.33%
        _seed(db_session, "F1", "RADICADA")
        _seed(db_session, "F1", "RADICADA")
        _seed(db_session, "F1", "LEVANTADA")
        # F2: 2 total, 2 cerradas → 100%
        _seed(db_session, "F2", "LEVANTADA")
        _seed(db_session, "F2", "ACEPTADA")

        r = client.get(
            "/glosas/stats/factura-tasa-cierre?min_glosas=1"
        )
        d = r.json()
        b = {it["factura"]: it for it in d["items"]}
        assert b["F1"]["pct_cerradas"] == 33.33
        assert b["F2"]["pct_cerradas"] == 100.0
