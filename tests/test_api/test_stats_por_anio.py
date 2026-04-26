"""Tests del endpoint GET /glosas/stats/por-anio (R157 P2)."""
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


def _seed(db, creado, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
    )
    base.update(kw)
    db.add(GlosaRecord(creado_en=creado, **base))
    db.commit()


class TestStatsPorAnio:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/por-anio")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["serie"] == []

    def test_creadas_y_cerradas_por_anio(self, client, db_session):
        # 2025: 1 creada
        _seed(db_session, datetime(2025, 6, 5, tzinfo=timezone.utc))
        # 2026: 2 creadas
        _seed(db_session, datetime(2026, 1, 1, tzinfo=timezone.utc))
        _seed(db_session,
              datetime(2026, 4, 1, tzinfo=timezone.utc),
              estado="LEVANTADA",
              valor_recuperado=5000,
              fecha_decision_eps=datetime(
                  2026, 4, 15, tzinfo=timezone.utc))

        r = client.get("/glosas/stats/por-anio")
        d = r.json()
        anios = {s["anio"]: s for s in d["serie"]}
        assert anios["2025"]["creadas"] == 1
        assert anios["2026"]["creadas"] == 2
        assert anios["2026"]["cerradas"] == 1
        assert anios["2026"]["valor_recuperado"] == 5000

    def test_serie_ascendente(self, client, db_session):
        _seed(db_session, datetime(2026, 1, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2024, 1, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2025, 1, 1, tzinfo=timezone.utc))
        r = client.get("/glosas/stats/por-anio")
        d = r.json()
        anios = [s["anio"] for s in d["serie"]]
        assert anios == ["2024", "2025", "2026"]
