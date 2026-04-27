"""Tests del endpoint GET /admin/auto-asignacion-sugerencias (R377 P1)."""
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


def _seed(db, eps="X", codigo="C", estado="RADICADA",
          gestor=None, valor=1000):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestAutoAsignacion:
    def test_sugiere_mejor_par(self, client, db_session):
        # Histórico (X, C): Alice 2/2, Bob 1/2
        _seed(db_session, gestor="Alice", estado="LEVANTADA")
        _seed(db_session, gestor="Alice", estado="LEVANTADA")
        _seed(db_session, gestor="Bob", estado="LEVANTADA")
        _seed(db_session, gestor="Bob", estado="RATIFICADA")
        # Glosa abierta sin gestor
        _seed(db_session, valor=5_000_000)

        r = client.get("/admin/auto-asignacion-sugerencias")
        d = r.json()
        item = next(
            x for x in d["items"]
            if x["valor_objetado"] == 5_000_000
        )
        assert item["gestor_sugerido"]["gestor"] == "Alice"
        assert item["gestor_sugerido"]["tasa_pct"] == 100.0
        assert item["gestor_sugerido"]["fuente"] == "par_eps_codigo"

    def test_sin_datos(self, client, db_session):
        _seed(db_session)  # única, sin gestor, sin histórico
        r = client.get("/admin/auto-asignacion-sugerencias")
        d = r.json()
        item = d["items"][0]
        assert item["gestor_sugerido"] is None
        assert "Sin datos" in item["razon"]
