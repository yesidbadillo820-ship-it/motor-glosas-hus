"""Regresión auditoría jun-2026 P2 #9: GET /historial aceptaba cualquier
`limit` (sin tope) — un limit=10_000_000 serializaba la tabla completa con
dictámenes HTML incluidos en una sola respuesta. Ahora Query(50, ge=1, le=500).
"""

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
def client(db_session):
    from app.api.deps import get_usuario_actual
    from app.main import app

    usuario = UsuarioRecord(id=1, email="admin@hus.gov.co", rol="ADMIN", activo=1)
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, n):
    for i in range(n):
        db.add(
            GlosaRecord(
                eps="FAMISANAR",
                paciente=f"PAC-{i}",
                codigo_glosa="TA0201",
                valor_objetado=100_000,
                valor_aceptado=0,
                etapa="RESPUESTA",
                estado="RADICADA",
                creado_en=ahora_utc(),
            )
        )
    db.commit()


class TestHistorialLimit:
    def test_limit_dentro_del_rango_funciona(self, client, db_session):
        _seed(db_session, 7)
        r = client.get("/glosas/historial?limit=5")
        assert r.status_code == 200
        assert len(r.json()) == 5

    def test_limit_default_50(self, client, db_session):
        _seed(db_session, 3)
        r = client.get("/glosas/historial")
        assert r.status_code == 200
        assert len(r.json()) == 3

    @pytest.mark.parametrize("limit", [501, 10_000, 10_000_000])
    def test_limit_excesivo_es_422(self, client, limit):
        r = client.get(f"/glosas/historial?limit={limit}")
        assert r.status_code == 422

    @pytest.mark.parametrize("limit", [0, -1])
    def test_limit_no_positivo_es_422(self, client, limit):
        r = client.get(f"/glosas/historial?limit={limit}")
        assert r.status_code == 422

    def test_limit_500_es_el_maximo_aceptado(self, client, db_session):
        _seed(db_session, 2)
        r = client.get("/glosas/historial?limit=500")
        assert r.status_code == 200
