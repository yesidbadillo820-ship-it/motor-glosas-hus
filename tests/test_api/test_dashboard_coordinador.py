"""Tests del endpoint GET /admin/dashboard-coordinador (R396 P1)."""
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


def _seed(db, eps="X", gestor=None, dias=10, estado="RADICADA",
          valor=1000, recuperado=0, decidida=False):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
        fecha_decision_eps=ahora_utc() if decidida else None,
    ))
    db.commit()


class TestDashboardCoordinador:
    def test_kpis(self, client, db_session):
        _seed(db_session, eps="SAN", gestor="Alice", dias=-3)
        _seed(db_session, eps="SAN", gestor=None, dias=10)
        _seed(
            db_session, eps="SAN", gestor="Alice",
            estado="LEVANTADA", recuperado=5000, decidida=True,
        )
        r = client.get("/admin/dashboard-coordinador")
        d = r.json()
        assert d["kpis"]["abiertas_total"] == 2
        assert d["kpis"]["vencidas"] == 1
        assert d["kpis"]["sin_gestor"] == 1
        assert d["kpis"]["decididas_mes"] == 1
        assert d["kpis"]["levantadas_mes"] == 1
        assert d["tasa_levantamiento_mes_pct"] == 100.0
        assert d["top_3_eps_volumen"][0]["eps"] == "SAN"

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
            r = c.get("/admin/dashboard-coordinador")
            assert r.status_code == 403
        app.dependency_overrides.clear()
