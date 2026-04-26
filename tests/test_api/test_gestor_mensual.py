"""Tests del endpoint GET /admin/gestor-mensual (R153 P1)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
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
def usuario_super(db_session):
    u = UsuarioRecord(
        id=1, email="root@hus.gov.co", rol="SUPER_ADMIN", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_super):
    from app.api.deps import get_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_admin] = lambda: usuario_super
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


class TestGestorMensual:
    def test_gestor_corto_400(self, client):
        r = client.get("/admin/gestor-mensual?gestor=A")
        assert r.status_code == 400

    def test_gestor_sin_glosas(self, client):
        r = client.get("/admin/gestor-mensual?gestor=Inexistente")
        d = r.json()
        assert d["total_meses_con_actividad"] == 0

    def test_serie_por_mes(self, client, db_session):
        _seed(db_session, "Alice",
              datetime(2026, 4, 5, tzinfo=timezone.utc))
        _seed(db_session, "Alice",
              datetime(2026, 3, 5, tzinfo=timezone.utc))

        r = client.get("/admin/gestor-mensual?gestor=Alice&meses=24")
        d = r.json()
        meses = [s["mes"] for s in d["serie"]]
        assert meses == sorted(meses)
        assert len(meses) == 2

    def test_aislamiento_por_gestor(self, client, db_session):
        _seed(db_session, "Alice",
              datetime(2026, 4, 5, tzinfo=timezone.utc))
        _seed(db_session, "Bob",
              datetime(2026, 4, 5, tzinfo=timezone.utc))

        r = client.get("/admin/gestor-mensual?gestor=Alice&meses=24")
        d = r.json()
        assert d["total_meses_con_actividad"] == 1

    def test_metricas(self, client, db_session):
        _seed(db_session, "Alice",
              datetime(2026, 4, 5, tzinfo=timezone.utc),
              estado="LEVANTADA", valor_rec=5000)
        _seed(db_session, "Alice",
              datetime(2026, 4, 10, tzinfo=timezone.utc),
              estado="ACEPTADA", valor_rec=0)

        r = client.get("/admin/gestor-mensual?gestor=Alice&meses=24")
        d = r.json()
        item = d["serie"][0]
        assert item["glosas_cerradas"] == 2
        assert item["levantadas"] == 1
        assert item["tasa_levantamiento_pct"] == 50.0
        assert item["valor_recuperado"] == 5000
