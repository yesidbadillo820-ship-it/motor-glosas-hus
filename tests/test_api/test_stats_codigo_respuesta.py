"""Tests del endpoint /glosas/stats/por-codigo-respuesta (R68 P1)."""
from __future__ import annotations

from datetime import timedelta

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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100_000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestStatsCodigoRespuesta:
    def test_sin_glosas(self, client):
        r = client.get("/glosas/stats/por-codigo-respuesta")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 0
        assert d["por_codigo"] == []

    def test_distribucion_basica(self, client, db_session):
        _seed(db_session, codigo_respuesta="RE9901", valor_objetado=100_000)
        _seed(db_session, codigo_respuesta="RE9901", valor_objetado=200_000)
        _seed(db_session, codigo_respuesta="RE9702", valor_objetado=50_000)
        r = client.get("/glosas/stats/por-codigo-respuesta")
        d = r.json()
        assert d["total"] == 3
        # RE9901 con 2, RE9702 con 1
        codigos = {x["codigo"]: x for x in d["por_codigo"]}
        assert codigos["RE9901"]["count"] == 2
        assert codigos["RE9702"]["count"] == 1

    def test_porcentajes_suman_100(self, client, db_session):
        _seed(db_session, codigo_respuesta="RE9901")
        _seed(db_session, codigo_respuesta="RE9701")
        _seed(db_session, codigo_respuesta="RE9801")
        _seed(db_session, codigo_respuesta="RE9702")
        r = client.get("/glosas/stats/por-codigo-respuesta")
        d = r.json()
        suma = sum(x["porcentaje"] for x in d["por_codigo"])
        # Aproximado a 100 (tolerancia por redondeo)
        assert abs(suma - 100.0) < 0.5

    def test_orden_por_count_desc(self, client, db_session):
        for _ in range(5):
            _seed(db_session, codigo_respuesta="RE9901")
        for _ in range(2):
            _seed(db_session, codigo_respuesta="RE9702")
        r = client.get("/glosas/stats/por-codigo-respuesta")
        d = r.json()
        # El más frecuente primero
        assert d["por_codigo"][0]["codigo"] == "RE9901"

    def test_descripciones_humanas(self, client, db_session):
        _seed(db_session, codigo_respuesta="RE9901")
        r = client.get("/glosas/stats/por-codigo-respuesta")
        d = r.json()
        # La descripción no debe ser solo el código
        desc = d["por_codigo"][0]["descripcion"]
        assert "no aceptada" in desc.lower() or "defensa" in desc.lower()

    def test_filtro_ventana_dias(self, client, db_session):
        _seed(db_session, codigo_respuesta="RE9901",
              creado_en=ahora_utc() - timedelta(days=60))
        _seed(db_session, codigo_respuesta="RE9702",
              creado_en=ahora_utc() - timedelta(days=2))
        # Default 30 días → solo el reciente
        r = client.get("/glosas/stats/por-codigo-respuesta?dias=30")
        d = r.json()
        assert d["total"] == 1
        assert d["por_codigo"][0]["codigo"] == "RE9702"
        # 90 días → ambos
        r = client.get("/glosas/stats/por-codigo-respuesta?dias=90")
        assert r.json()["total"] == 2
