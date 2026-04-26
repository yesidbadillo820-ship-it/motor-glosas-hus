"""Tests del endpoint GET /glosas/{id}/sla (R92 P2)."""
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


class TestGlosaSLA:
    def test_404_inexistente(self, client):
        r = client.get("/glosas/99999/sla")
        assert r.status_code == 404

    def test_sin_vencimiento(self, client, db_session):
        g = _seed(db_session, fecha_vencimiento=None)
        r = client.get(f"/glosas/{g.id}/sla")
        d = r.json()
        assert d["estado_sla"] == "SIN_VENCIMIENTO"
        assert d["color_semaforo"] == "GRIS"

    def test_en_tiempo(self, client, db_session):
        g = _seed(db_session,
                  fecha_vencimiento=ahora_utc() + timedelta(days=20),
                  dias_restantes=20)
        r = client.get(f"/glosas/{g.id}/sla")
        d = r.json()
        assert d["estado_sla"] == "EN_TIEMPO"
        assert d["color_semaforo"] == "VERDE"
        assert d["cerrada"] is False

    def test_critica(self, client, db_session):
        g = _seed(db_session,
                  fecha_vencimiento=ahora_utc() + timedelta(days=2),
                  dias_restantes=2)
        r = client.get(f"/glosas/{g.id}/sla")
        d = r.json()
        assert d["estado_sla"] == "CRITICA"
        assert d["color_semaforo"] == "AMARILLO"

    def test_vencida(self, client, db_session):
        g = _seed(db_session,
                  fecha_vencimiento=ahora_utc() - timedelta(days=5),
                  dias_restantes=-5)
        r = client.get(f"/glosas/{g.id}/sla")
        d = r.json()
        assert d["estado_sla"] == "VENCIDA"
        assert d["color_semaforo"] == "ROJO"

    def test_cerrada_a_tiempo(self, client, db_session):
        ahora = ahora_utc()
        g = _seed(db_session,
                  estado="LEVANTADA",
                  fecha_vencimiento=ahora + timedelta(days=2),
                  fecha_decision_eps=ahora - timedelta(days=1))
        r = client.get(f"/glosas/{g.id}/sla")
        d = r.json()
        assert d["estado_sla"] == "CERRADA_A_TIEMPO"
        assert d["color_semaforo"] == "VERDE"
        assert d["cerrada"] is True

    def test_cerrada_tarde(self, client, db_session):
        ahora = ahora_utc()
        g = _seed(db_session,
                  estado="ACEPTADA",
                  fecha_vencimiento=ahora - timedelta(days=10),
                  fecha_decision_eps=ahora - timedelta(days=2))
        r = client.get(f"/glosas/{g.id}/sla")
        d = r.json()
        assert d["estado_sla"] == "CERRADA_TARDE"
        assert d["color_semaforo"] == "NEGRO"

    def test_tiempo_total_resolucion(self, client, db_session):
        ahora = ahora_utc()
        g = _seed(db_session,
                  estado="LEVANTADA",
                  creado_en=ahora - timedelta(days=20),
                  fecha_decision_eps=ahora,
                  fecha_vencimiento=ahora + timedelta(days=5))
        r = client.get(f"/glosas/{g.id}/sla")
        d = r.json()
        assert d["tiempo_total_resolucion_dias"] == 20
