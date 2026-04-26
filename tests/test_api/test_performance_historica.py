"""Tests del endpoint GET /usuarios/yo/performance-historica (R145 P2)."""
from __future__ import annotations

from datetime import datetime, timezone

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


def _seed(db, gestor, fecha_dec, estado="LEVANTADA", valor_rec=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        fecha_decision_eps=fecha_dec,
    ))
    db.commit()


class TestPerformanceHistorica:
    def test_estructura(self, client):
        r = client.get("/usuarios/yo/performance-historica")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("usuario_email", "ventana_meses",
                    "total_meses_con_actividad", "serie"):
            assert key in d

    def test_solo_glosas_propias(self, client, db_session):
        _seed(db_session, "Alice",
              datetime(2026, 4, 5, tzinfo=timezone.utc))
        _seed(db_session, "Bob",
              datetime(2026, 4, 5, tzinfo=timezone.utc))

        r = client.get("/usuarios/yo/performance-historica?meses=24")
        d = r.json()
        # Solo Alice → 1 mes con actividad
        assert d["serie"][0]["glosas_cerradas"] == 1

    def test_agrupa_por_mes(self, client, db_session):
        _seed(db_session, "Alice",
              datetime(2026, 4, 5, tzinfo=timezone.utc))
        _seed(db_session, "Alice",
              datetime(2026, 4, 20, tzinfo=timezone.utc))
        _seed(db_session, "Alice",
              datetime(2026, 3, 1, tzinfo=timezone.utc))

        r = client.get("/usuarios/yo/performance-historica?meses=24")
        d = r.json()
        meses = {s["mes"]: s for s in d["serie"]}
        assert meses["2026-04"]["glosas_cerradas"] == 2
        assert meses["2026-03"]["glosas_cerradas"] == 1

    def test_tasa_levantamiento(self, client, db_session):
        # 2 LEVANTADA + 1 ACEPTADA en abril → 66.67%
        _seed(db_session, "Alice",
              datetime(2026, 4, 1, tzinfo=timezone.utc),
              estado="LEVANTADA")
        _seed(db_session, "Alice",
              datetime(2026, 4, 5, tzinfo=timezone.utc),
              estado="LEVANTADA")
        _seed(db_session, "Alice",
              datetime(2026, 4, 10, tzinfo=timezone.utc),
              estado="ACEPTADA")
        r = client.get("/usuarios/yo/performance-historica?meses=24")
        d = r.json()
        abril = next(s for s in d["serie"] if s["mes"] == "2026-04")
        assert abril["tasa_levantamiento_pct"] == 66.67

    def test_serie_ascendente(self, client, db_session):
        for mes in (1, 4, 3):
            _seed(db_session, "Alice",
                  datetime(2026, mes, 5, tzinfo=timezone.utc))
        r = client.get("/usuarios/yo/performance-historica?meses=24")
        d = r.json()
        meses = [s["mes"] for s in d["serie"]]
        assert meses == sorted(meses)
