"""Tests del endpoint GET /glosas/stats/codigos-respuesta-mejor-tasa-eps (R398 P1)."""
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
    return UsuarioRecord(id=1, email="x@x", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, eps, codigo_respuesta, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        codigo_respuesta=codigo_respuesta,
    ))
    db.commit()


class TestCodigosMejorTasa:
    def test_orden(self, client, db_session):
        # SAN: RE9501 → 100% (2/2)
        _seed(db_session, "SAN", "RE9501", "LEVANTADA")
        _seed(db_session, "SAN", "RE9501", "LEVANTADA")
        # SAN: RE9701 → 0% (0/2)
        _seed(db_session, "SAN", "RE9701", "RATIFICADA")
        _seed(db_session, "SAN", "RE9701", "RATIFICADA")
        r = client.get(
            "/glosas/stats/codigos-respuesta-mejor-tasa-eps?eps=SAN"
        )
        d = r.json()
        assert d["items"][0]["codigo_respuesta"] == "RE9501"
        assert d["items"][0]["tasa_levantamiento_pct"] == 100.0
        assert d["items"][1]["tasa_levantamiento_pct"] == 0.0

    def test_min_muestras(self, client, db_session):
        _seed(db_session, "SAN", "RE9501", "LEVANTADA")
        # solo 1 muestra, no califica
        r = client.get(
            "/glosas/stats/codigos-respuesta-mejor-tasa-eps?eps=SAN&min_muestras=2"
        )
        d = r.json()
        assert d["items"] == []
