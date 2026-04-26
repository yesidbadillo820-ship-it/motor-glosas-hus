"""Tests del endpoint GET /glosas/stats/proyeccion-recuperacion (R102 P2)."""
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


def _seed(db, estado, valor_obj, valor_rec=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor_obj, valor_recuperado=valor_rec,
        etapa="X", estado=estado, creado_en=ahora_utc(),
    ))
    db.commit()


class TestProyeccionRecuperacion:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/proyeccion-recuperacion")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["tasa_historica_recuperacion_pct"] == 0.0
        assert d["valor_pendiente_total"] == 0
        assert d["proyeccion_recuperable"] == 0

    def test_proyeccion_basada_en_tasa_historica(self, client, db_session):
        # Histórico cerrado: 50% de recuperación
        _seed(db_session, "LEVANTADA", valor_obj=10_000, valor_rec=10_000)
        _seed(db_session, "ACEPTADA", valor_obj=10_000, valor_rec=0)
        # Pendientes: 20_000
        _seed(db_session, "RADICADA", valor_obj=10_000)
        _seed(db_session, "RADICADA", valor_obj=10_000)

        r = client.get("/glosas/stats/proyeccion-recuperacion")
        d = r.json()
        assert d["tasa_historica_recuperacion_pct"] == 50.0
        assert d["valor_pendiente_total"] == 20_000
        assert d["glosas_pendientes"] == 2
        # Proyección = 20_000 * 0.50 = 10_000
        assert d["proyeccion_recuperable"] == 10_000

    def test_intervalo_20_pct(self, client, db_session):
        _seed(db_session, "LEVANTADA", valor_obj=10_000, valor_rec=10_000)
        _seed(db_session, "RADICADA", valor_obj=10_000)
        r = client.get("/glosas/stats/proyeccion-recuperacion")
        d = r.json()
        # Tasa = 100%, pendiente = 10_000, proyeccion = 10_000
        # Intervalo: 8_000 - 12_000
        assert d["intervalo"]["min"] == 8000
        assert d["intervalo"]["max"] == 12000
        assert d["intervalo"]["margen_pct"] == 20

    def test_sin_historico_proyeccion_cero(self, client, db_session):
        # Solo pendientes, sin cerradas para calcular tasa
        _seed(db_session, "RADICADA", valor_obj=50_000)
        r = client.get("/glosas/stats/proyeccion-recuperacion")
        d = r.json()
        assert d["tasa_historica_recuperacion_pct"] == 0.0
        # Sin tasa histórica, proyeccion = 0 (no se puede predecir)
        assert d["proyeccion_recuperable"] == 0
        assert d["valor_pendiente_total"] == 50_000
