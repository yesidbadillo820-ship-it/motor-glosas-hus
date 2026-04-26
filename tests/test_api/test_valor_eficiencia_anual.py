"""Tests del endpoint GET /glosas/stats/valor-eficiencia-anual (R210 P1)."""
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


def _seed(db, fecha, obj, rec):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=obj, valor_recuperado=rec,
        etapa="X", estado="LEVANTADA",
        creado_en=fecha,
    ))
    db.commit()


class TestValorEficienciaAnual:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/valor-eficiencia-anual")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "serie" in d

    def test_eficiencia_anual(self, client, db_session):
        _seed(db_session,
              datetime(2025, 6, 1, tzinfo=timezone.utc),
              obj=10_000_000, rec=5_000_000)
        _seed(db_session,
              datetime(2026, 1, 1, tzinfo=timezone.utc),
              obj=4_000_000, rec=3_000_000)

        r = client.get("/glosas/stats/valor-eficiencia-anual")
        d = r.json()
        anios = {s["anio"]: s for s in d["serie"]}
        assert anios["2025"]["eficiencia_pct"] == 50.0
        assert anios["2026"]["eficiencia_pct"] == 75.0

    def test_serie_ascendente(self, client, db_session):
        _seed(db_session, datetime(2026, 1, 1, tzinfo=timezone.utc),
              obj=100, rec=0)
        _seed(db_session, datetime(2024, 1, 1, tzinfo=timezone.utc),
              obj=100, rec=0)
        r = client.get("/glosas/stats/valor-eficiencia-anual")
        d = r.json()
        anios = [s["anio"] for s in d["serie"]]
        assert anios == sorted(anios)
