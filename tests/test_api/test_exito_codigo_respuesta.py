"""Tests del endpoint GET /glosas/stats/exito-por-codigo-respuesta (R116 P1)."""
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


def _seed(db, codigo_respuesta, estado):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        codigo_respuesta=codigo_respuesta,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestExitoCodigoRespuesta:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/exito-por-codigo-respuesta")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_excluye_glosas_sin_codigo_respuesta(self, client, db_session):
        _seed(db_session, None, "LEVANTADA")
        r = client.get("/glosas/stats/exito-por-codigo-respuesta")
        d = r.json()
        assert d["items"] == []

    def test_tasa_levantamiento(self, client, db_session):
        # RE9502 usado 4 veces, 3 levantadas + 1 ratificada → 75%
        for _ in range(3):
            _seed(db_session, "RE9502", "LEVANTADA")
        _seed(db_session, "RE9502", "RATIFICADA")
        r = client.get("/glosas/stats/exito-por-codigo-respuesta")
        d = r.json()
        item = next(it for it in d["items"]
                    if it["codigo_respuesta"] == "RE9502")
        assert item["total_usado"] == 4
        assert item["decididas"] == 4
        assert item["tasa_levantamiento_pct"] == 75.0

    def test_orden_por_tasa_desc(self, client, db_session):
        # RE9502: 100% éxito
        _seed(db_session, "RE9502", "LEVANTADA")
        # RE9801: 0% éxito
        _seed(db_session, "RE9801", "RATIFICADA")
        r = client.get("/glosas/stats/exito-por-codigo-respuesta")
        d = r.json()
        assert d["items"][0]["codigo_respuesta"] == "RE9502"
        assert d["items"][1]["codigo_respuesta"] == "RE9801"

    def test_pendientes_no_cuentan_para_tasa(self, client, db_session):
        _seed(db_session, "RE9502", "RADICADA")  # pendiente
        _seed(db_session, "RE9502", "LEVANTADA")  # decidida
        r = client.get("/glosas/stats/exito-por-codigo-respuesta")
        d = r.json()
        item = d["items"][0]
        assert item["total_usado"] == 2
        assert item["decididas"] == 1  # solo la LEVANTADA cuenta
        assert item["tasa_levantamiento_pct"] == 100.0
