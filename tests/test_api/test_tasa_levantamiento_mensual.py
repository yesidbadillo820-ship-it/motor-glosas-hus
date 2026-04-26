"""Tests del endpoint GET /glosas/stats/tasa-levantamiento-mensual (R232 P1)."""
from __future__ import annotations

from datetime import datetime, timezone

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


def _seed(db, fecha_dec, estado):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=fecha_dec,
    ))
    db.commit()


class TestTasaLevantamientoMensual:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/tasa-levantamiento-mensual")
        d = r.json()
        for key in ("meses_solicitados", "serie"):
            assert key in d

    def test_evolucion(self, client, db_session):
        # Marzo: 1 LEV / 2 = 50%
        _seed(db_session,
              datetime(2026, 3, 5, tzinfo=timezone.utc),
              "LEVANTADA")
        _seed(db_session,
              datetime(2026, 3, 10, tzinfo=timezone.utc),
              "ACEPTADA")
        # Abril: 3 LEV / 4 = 75%
        for _ in range(3):
            _seed(db_session,
                  datetime(2026, 4, 1, tzinfo=timezone.utc),
                  "LEVANTADA")
        _seed(db_session,
              datetime(2026, 4, 15, tzinfo=timezone.utc),
              "ACEPTADA")

        r = client.get(
            "/glosas/stats/tasa-levantamiento-mensual?meses=24"
        )
        d = r.json()
        meses = {s["mes"]: s for s in d["serie"]}
        assert meses["2026-03"]["tasa_levantamiento_pct"] == 50.0
        assert meses["2026-04"]["tasa_levantamiento_pct"] == 75.0
