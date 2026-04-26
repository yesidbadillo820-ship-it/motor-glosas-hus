"""Tests del endpoint GET /glosas/stats/abandono-por-etapa (R106 P1)."""
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


def _seed(db, etapa, estado, dias_atras=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa=etapa, estado=estado,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestAbandonoEtapa:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/abandono-por-etapa")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_clasifica_por_etapa(self, client, db_session):
        _seed(db_session, "RESPUESTA_PRIMERA", "RADICADA")
        _seed(db_session, "RESPUESTA_PRIMERA", "RADICADA")
        _seed(db_session, "RATIFICACION", "RADICADA")
        r = client.get("/glosas/stats/abandono-por-etapa")
        d = r.json()
        etapas = {it["etapa"]: it for it in d["items"]}
        assert etapas["RESPUESTA_PRIMERA"]["total_glosas"] == 2
        assert etapas["RATIFICACION"]["total_glosas"] == 1

    def test_tasa_abandono(self, client, db_session):
        # 3 abiertas + 1 cerrada en RESPUESTA_PRIMERA → 75% abandono
        for _ in range(3):
            _seed(db_session, "RESPUESTA_PRIMERA", "RADICADA")
        _seed(db_session, "RESPUESTA_PRIMERA", "LEVANTADA")
        r = client.get("/glosas/stats/abandono-por-etapa")
        d = r.json()
        item = next(it for it in d["items"]
                    if it["etapa"] == "RESPUESTA_PRIMERA")
        assert item["abiertas"] == 3
        assert item["total_glosas"] == 4
        assert item["tasa_abandono_pct"] == 75.0

    def test_orden_desc_por_tasa(self, client, db_session):
        # Etapa A: 100% abandono
        _seed(db_session, "A", "RADICADA")
        # Etapa B: 50% abandono
        _seed(db_session, "B", "RADICADA")
        _seed(db_session, "B", "ACEPTADA")
        r = client.get("/glosas/stats/abandono-por-etapa")
        d = r.json()
        assert d["items"][0]["etapa"] == "A"
        assert d["items"][0]["tasa_abandono_pct"] == 100.0
        assert d["items"][1]["etapa"] == "B"
        assert d["items"][1]["tasa_abandono_pct"] == 50.0

    def test_tiempo_promedio_solo_abiertas(self, client, db_session):
        # Glosa abierta hace 30d
        _seed(db_session, "X", "RADICADA", dias_atras=30)
        # Glosa cerrada hace 100d (NO debe afectar tiempo_promedio)
        _seed(db_session, "X", "ACEPTADA", dias_atras=100)
        r = client.get("/glosas/stats/abandono-por-etapa")
        d = r.json()
        item = next(it for it in d["items"] if it["etapa"] == "X")
        # Solo la abierta cuenta para tiempo promedio
        assert 29 <= item["tiempo_promedio_dias_abiertas"] <= 31
