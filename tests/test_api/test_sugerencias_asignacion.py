"""Tests del endpoint GET /admin/sugerencias-asignacion (R315 P1)."""
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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gestor, eps, estado):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestSugerenciasAsignacion:
    def test_ranking(self, client, db_session):
        # Alice: 2/2 con SANITAS → 100%
        _seed(db_session, "Alice", "SANITAS", "LEVANTADA")
        _seed(db_session, "Alice", "SANITAS", "LEVANTADA")
        # Bob: 1/2 con SANITAS → 50%
        _seed(db_session, "Bob", "SANITAS", "LEVANTADA")
        _seed(db_session, "Bob", "SANITAS", "RATIFICADA")
        # Carla con OTRA, no debe aparecer
        _seed(db_session, "Carla", "OTRA", "LEVANTADA")

        r = client.get("/admin/sugerencias-asignacion?eps=SANITAS")
        d = r.json()
        assert d["total_gestores_con_historial"] == 2
        assert d["items"][0]["gestor"] == "Alice"
        assert d["items"][0]["tasa_levantamiento_pct"] == 100.0
        assert d["items"][1]["gestor"] == "Bob"
        assert d["items"][1]["tasa_levantamiento_pct"] == 50.0
