"""Tests del endpoint GET /admin/balance-carga-gestores (R379 P1)."""
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
def admin():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gestor, dias=10):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
    ))
    db.commit()


class TestBalanceCarga:
    def test_clasifica(self, client, db_session):
        # Alice: 20 abiertas (sobrecargada)
        for _ in range(20):
            _seed(db_session, "Alice")
        # Bob: 5 (normal)
        for _ in range(5):
            _seed(db_session, "Bob")
        # Carla: 1 (subcargada)
        _seed(db_session, "Carla")

        r = client.get("/admin/balance-carga-gestores")
        d = r.json()
        b = {it["gestor"]: it for it in d["items"]}
        assert b["Alice"]["estado_carga"] == "SOBRECARGADO"
        assert b["Carla"]["estado_carga"] == "SUBCARGADO"

    def test_vacio(self, client):
        r = client.get("/admin/balance-carga-gestores")
        d = r.json()
        assert d["total_gestores"] == 0
