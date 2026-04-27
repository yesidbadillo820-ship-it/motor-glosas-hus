"""Tests del endpoint GET /admin/equipo-pulse (R384 P1)."""
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


def _seed(db, gestor=None, dias=10):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
    ))
    db.commit()


class TestEquipoPulse:
    def test_resumen(self, client, db_session):
        # Alice mucho carga, Bob/Carla normales para que mediana
        # quede en algo bajo y Alice se considere sobrecargada
        for _ in range(20):
            _seed(db_session, gestor="Alice")
        _seed(db_session, gestor="Alice", dias=-3)
        for _ in range(3):
            _seed(db_session, gestor="Bob")
        for _ in range(3):
            _seed(db_session, gestor="Carla")
        _seed(db_session, gestor=None)
        r = client.get("/admin/equipo-pulse")
        d = r.json()
        assert d["total_gestores_con_carga"] == 3
        assert d["abiertas_totales"] == 28
        assert d["vencidas_globales"] >= 1
        assert d["glosas_sin_gestor"] == 1
        assert any(
            x["gestor"] == "Alice" for x in d["sobrecargados"]
        )

    def test_no_admin_403(self, db_session):
        from app.api.deps import get_usuario_actual
        from app.main import app
        no_admin = UsuarioRecord(
            id=99, email="x@x", rol="AUDITOR", activo=1,
        )
        app.dependency_overrides[get_db] = (
            lambda: iter([db_session]).__next__()
        )
        app.dependency_overrides[get_usuario_actual] = lambda: no_admin
        with TestClient(app) as c:
            r = c.get("/admin/equipo-pulse")
            assert r.status_code == 403
        app.dependency_overrides.clear()
