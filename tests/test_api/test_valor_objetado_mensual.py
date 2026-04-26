"""Tests del endpoint GET /glosas/stats/valor-objetado-mensual (R172 P1)."""
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


def _seed(db, fecha, valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=fecha,
    ))
    db.commit()


class TestValorObjetadoMensual:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/valor-objetado-mensual")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["serie"] == []

    def test_serie_basica(self, client, db_session):
        _seed(db_session,
              datetime(2026, 4, 5, tzinfo=timezone.utc),
              valor=10_000)
        _seed(db_session,
              datetime(2026, 4, 20, tzinfo=timezone.utc),
              valor=20_000)
        _seed(db_session,
              datetime(2026, 3, 1, tzinfo=timezone.utc),
              valor=5_000)

        r = client.get("/glosas/stats/valor-objetado-mensual?meses=24")
        d = r.json()
        meses = {s["mes"]: s for s in d["serie"]}
        assert meses["2026-04"]["count_glosas"] == 2
        assert meses["2026-04"]["valor_objetado_total"] == 30_000
        assert meses["2026-04"]["valor_promedio"] == 15000.0
        assert meses["2026-03"]["valor_objetado_total"] == 5000

    def test_serie_ascendente(self, client, db_session):
        _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 1, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 3, 1, tzinfo=timezone.utc))
        r = client.get("/glosas/stats/valor-objetado-mensual?meses=24")
        d = r.json()
        meses = [s["mes"] for s in d["serie"]]
        assert meses == sorted(meses)
