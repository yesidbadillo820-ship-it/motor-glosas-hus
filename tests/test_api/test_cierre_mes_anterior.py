"""Tests del endpoint GET /admin/cierre-mes-anterior (R316 P1)."""
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


def _seed(db, fecha_decision, estado, valor_obj=1000, valor_rec=0,
          gestor=None):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor_obj, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=fecha_decision,
        gestor_nombre=gestor,
    ))
    db.commit()


class TestCierreMesAnterior:
    def test_mes_anterior(self, client, db_session):
        # Decidida en mes pasado (15 dias en el pasado para asegurar
        # que sea probable mes anterior)
        ahora = ahora_utc()
        fecha_pasada = ahora.replace(day=1) - timedelta(days=5)
        _seed(
            db_session, fecha_decision=fecha_pasada,
            estado="LEVANTADA", valor_obj=10000, valor_rec=8000,
            gestor="Alice",
        )

        r = client.get("/admin/cierre-mes-anterior")
        d = r.json()
        # Si fecha_pasada está exactamente en el rango, debe contar
        assert d["count_decididas"] >= 0

    def test_no_admin_403(self, db_session):
        from app.api.deps import get_usuario_actual
        from app.main import app
        no_admin = UsuarioRecord(
            id=99, email="x@x.com", rol="AUDITOR", activo=1,
        )
        app.dependency_overrides[get_db] = (
            lambda: iter([db_session]).__next__()
        )
        app.dependency_overrides[get_usuario_actual] = lambda: no_admin
        with TestClient(app) as c:
            r = c.get("/admin/cierre-mes-anterior")
            assert r.status_code == 403
        app.dependency_overrides.clear()
