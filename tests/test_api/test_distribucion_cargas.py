"""Tests del endpoint GET /admin/distribucion-cargas (R95 P2)."""
from __future__ import annotations

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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestDistribucionCargas:
    def test_vacio(self, client):
        r = client.get("/admin/distribucion-cargas")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_gestores"] == 0
        assert d["total_glosas_abiertas"] == 0
        assert d["items"] == []

    def test_agrupa_por_gestor(self, client, db_session):
        for _ in range(3):
            _seed(db_session, gestor_nombre="Alice")
        for _ in range(5):
            _seed(db_session, gestor_nombre="Bob")
        _seed(db_session, gestor_nombre=None)  # SIN_ASIGNAR

        r = client.get("/admin/distribucion-cargas")
        d = r.json()
        # Bob primero (5 > 3 > 1)
        assert d["items"][0]["gestor"] == "Bob"
        assert d["items"][0]["total_glosas"] == 5
        assert d["items"][1]["gestor"] == "Alice"
        assert d["items"][2]["gestor"] == "SIN_ASIGNAR"

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, gestor_nombre="Alice", estado="RADICADA")
        _seed(db_session, gestor_nombre="Alice", estado="ACEPTADA")
        _seed(db_session, gestor_nombre="Alice", estado="LEVANTADA")
        r = client.get("/admin/distribucion-cargas")
        d = r.json()
        item = next(it for it in d["items"] if it["gestor"] == "Alice")
        # Solo la RADICADA cuenta
        assert item["total_glosas"] == 1

    def test_clasifica_vencidas_y_criticas(self, client, db_session):
        _seed(db_session, gestor_nombre="Alice", dias_restantes=-5)
        _seed(db_session, gestor_nombre="Alice", dias_restantes=-1)
        _seed(db_session, gestor_nombre="Alice", dias_restantes=2)
        _seed(db_session, gestor_nombre="Alice", dias_restantes=10)
        r = client.get("/admin/distribucion-cargas")
        d = r.json()
        item = next(it for it in d["items"] if it["gestor"] == "Alice")
        assert item["total_glosas"] == 4
        assert item["vencidas"] == 2
        assert item["criticas"] == 1
        # tasa_atraso_pct = 2/4 = 50%
        assert item["tasa_atraso_pct"] == 50.0

    def test_acumula_valor_objetado(self, client, db_session):
        _seed(db_session, gestor_nombre="Alice", valor_objetado=1000)
        _seed(db_session, gestor_nombre="Alice", valor_objetado=2500)
        r = client.get("/admin/distribucion-cargas")
        d = r.json()
        item = next(it for it in d["items"] if it["gestor"] == "Alice")
        assert item["valor_objetado_total"] == 3500
