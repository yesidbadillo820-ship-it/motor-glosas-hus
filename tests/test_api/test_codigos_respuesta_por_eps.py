"""Tests del endpoint GET /glosas/stats/codigos-respuesta-por-eps (R145 P1)."""
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


def _seed(db, eps, codigo_respuesta, estado):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        codigo_respuesta=codigo_respuesta,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestCodigosRespuestaPorEPS:
    def test_query_minima(self, client):
        r = client.get("/glosas/stats/codigos-respuesta-por-eps?eps=A")
        assert r.status_code == 422

    def test_eps_sin_glosas(self, client):
        r = client.get(
            "/glosas/stats/codigos-respuesta-por-eps?eps=Inexistente"
        )
        d = r.json()
        assert d["items"] == []

    def test_filtro_estricto_por_eps(self, client, db_session):
        # SANITAS con RE9502 LEVANTADA
        _seed(db_session, "SANITAS", "RE9502", "LEVANTADA")
        # NUEVA EPS con RE9502 RATIFICADA — no debe entrar
        _seed(db_session, "NUEVA EPS", "RE9502", "RATIFICADA")

        r = client.get(
            "/glosas/stats/codigos-respuesta-por-eps?eps=SANITAS"
        )
        d = r.json()
        item = d["items"][0]
        assert item["codigo_respuesta"] == "RE9502"
        assert item["levantadas"] == 1
        assert item["tasa_levantamiento_pct"] == 100.0

    def test_orden_por_tasa_desc(self, client, db_session):
        # RE9502: 100% éxito
        _seed(db_session, "SANITAS", "RE9502", "LEVANTADA")
        # RE9801: 0% éxito
        _seed(db_session, "SANITAS", "RE9801", "RATIFICADA")
        r = client.get(
            "/glosas/stats/codigos-respuesta-por-eps?eps=SANITAS"
        )
        d = r.json()
        assert d["items"][0]["codigo_respuesta"] == "RE9502"
        assert d["items"][1]["codigo_respuesta"] == "RE9801"

    def test_eps_devuelve_eco(self, client):
        r = client.get(
            "/glosas/stats/codigos-respuesta-por-eps?eps=SANITAS"
        )
        d = r.json()
        assert d["eps"] == "SANITAS"
