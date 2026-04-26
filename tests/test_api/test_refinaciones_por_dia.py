"""Tests del endpoint GET /glosas/stats/refinaciones-por-dia (R193 P1)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import DictamenVersionRecord, UsuarioRecord


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


def _seed(db, fecha, accion="REFINAR"):
    db.add(DictamenVersionRecord(
        glosa_id=1, dictamen_html="<p>X</p>",
        accion=accion, creado_en=fecha,
    ))
    db.commit()


class TestRefinacionesPorDia:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/refinaciones-por-dia")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "total_acciones", "serie"):
            assert key in d

    def test_agrupa_por_fecha(self, client, db_session):
        _seed(db_session,
              ahora_utc().replace(microsecond=0))
        _seed(db_session,
              ahora_utc().replace(microsecond=0))
        # Ayer
        from datetime import timedelta
        ayer = ahora_utc() - timedelta(days=1)
        _seed(db_session, ayer.replace(microsecond=0))

        r = client.get("/glosas/stats/refinaciones-por-dia")
        d = r.json()
        # 2 días con actividad
        assert len(d["serie"]) == 2

    def test_desglose_por_accion(self, client, db_session):
        _seed(db_session, ahora_utc(), accion="REFINAR")
        _seed(db_session, ahora_utc(), accion="REFINAR")
        _seed(db_session, ahora_utc(), accion="REGENERAR")

        r = client.get("/glosas/stats/refinaciones-por-dia")
        d = r.json()
        item = d["serie"][-1]
        assert item["total"] == 3
        assert item["refinar"] == 2
        assert item["regenerar"] == 1
