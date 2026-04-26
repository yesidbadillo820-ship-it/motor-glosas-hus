"""Tests del endpoint GET /usuarios/yo/resumen (R123 P2)."""
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
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice", rol="AUDITOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gestor, estado="RADICADA", **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(gestor_nombre=gestor, estado=estado, **base))
    db.commit()


class TestResumenPersonal:
    def test_estructura(self, client):
        r = client.get("/usuarios/yo/resumen")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("usuario_email", "ventana_dias",
                    "mis_glosas_asignadas",
                    "mis_glosas_cerradas_periodo",
                    "mi_valor_recuperado_periodo",
                    "mi_tasa_levantamiento_pct",
                    "mi_tiempo_promedio_resolucion_dias",
                    "posicion_ranking"):
            assert key in d

    def test_solo_mis_glosas(self, client, db_session):
        _seed(db_session, "Alice")
        _seed(db_session, "Alice")
        _seed(db_session, "Bob")  # no cuenta
        r = client.get("/usuarios/yo/resumen")
        d = r.json()
        assert d["mis_glosas_asignadas"] == 2

    def test_cerradas_y_recuperado(self, client, db_session):
        _seed(db_session, "Alice", estado="LEVANTADA",
              valor_recuperado=5000,
              fecha_decision_eps=ahora_utc() - timedelta(days=10))
        # Cerrada hace 60 días (fuera de ventana 30d)
        _seed(db_session, "Alice", estado="LEVANTADA",
              valor_recuperado=99999,
              fecha_decision_eps=ahora_utc() - timedelta(days=60))

        r = client.get("/usuarios/yo/resumen")
        d = r.json()
        assert d["mis_glosas_cerradas_periodo"] == 1
        assert d["mi_valor_recuperado_periodo"] == 5000

    def test_tasa_levantamiento(self, client, db_session):
        # 1 levantada / 2 decididas = 50%
        _seed(db_session, "Alice", estado="LEVANTADA",
              fecha_decision_eps=ahora_utc() - timedelta(days=5))
        _seed(db_session, "Alice", estado="ACEPTADA",
              fecha_decision_eps=ahora_utc() - timedelta(days=5))
        r = client.get("/usuarios/yo/resumen")
        d = r.json()
        assert d["mi_tasa_levantamiento_pct"] == 50.0

    def test_posicion_ranking(self, client, db_session):
        # Bob: 5 levantamientos
        for _ in range(5):
            _seed(db_session, "Bob", estado="LEVANTADA",
                  fecha_decision_eps=ahora_utc() - timedelta(days=5))
        # Alice: 2 levantamientos
        for _ in range(2):
            _seed(db_session, "Alice", estado="LEVANTADA",
                  fecha_decision_eps=ahora_utc() - timedelta(days=5))
        # Carol: 1
        _seed(db_session, "Carol", estado="LEVANTADA",
              fecha_decision_eps=ahora_utc() - timedelta(days=5))

        r = client.get("/usuarios/yo/resumen")
        d = r.json()
        # Alice está en posición 2 (Bob es #1)
        assert d["posicion_ranking"] == 2
