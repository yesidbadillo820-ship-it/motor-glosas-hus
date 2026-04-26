"""Tests del endpoint GET /glosas/stats/conciliaciones (R128 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import ConciliacionRecord, GlosaRecord, UsuarioRecord


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


def _seed_glosa(db, glosa_id):
    db.add(GlosaRecord(
        id=glosa_id, eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_conc(db, glosa_id, **kw):
    base = dict(
        glosa_id=glosa_id, creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(ConciliacionRecord(**base))
    db.commit()


class TestStatsConciliaciones:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/conciliaciones")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_conciliaciones"] == 0
        assert d["por_resultado"] == {}
        assert d["valor_total_conciliado"] == 0

    def test_estructura(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_conc(db_session, 1,
                   resultado="ACEPTADA",
                   estado_bilateral="ACTA_FIRMADA",
                   valor_conciliado=5000,
                   valor_ratificado_hus=10000)
        r = client.get("/glosas/stats/conciliaciones")
        d = r.json()
        assert d["total_conciliaciones"] == 1
        assert d["por_resultado"] == {"ACEPTADA": 1}
        assert d["por_estado_bilateral"] == {"ACTA_FIRMADA": 1}
        assert d["valor_total_conciliado"] == 5000
        assert d["valor_total_defendido_hus"] == 10000
        # 5000 / 10000 = 50%
        assert d["tasa_recuperacion_conciliacion_pct"] == 50.0

    def test_audiencias_proximas(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        _seed_glosa(db_session, 3)
        # En 10 días
        _seed_conc(db_session, 1,
                   fecha_audiencia=ahora_utc() + timedelta(days=10))
        # En 50 días (fuera)
        _seed_conc(db_session, 2,
                   fecha_audiencia=ahora_utc() + timedelta(days=50))
        # Pasada
        _seed_conc(db_session, 3,
                   fecha_audiencia=ahora_utc() - timedelta(days=5))

        r = client.get("/glosas/stats/conciliaciones")
        d = r.json()
        assert d["audiencias_proximas_30d"] == 1
