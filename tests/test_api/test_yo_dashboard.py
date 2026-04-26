"""Tests del endpoint GET /usuarios/yo/dashboard (R255 P1)."""
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


def _seed(db, gestor="Alice", **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(gestor_nombre=gestor, **base))
    db.commit()


class TestYoDashboard:
    def test_estructura(self, client):
        r = client.get("/usuarios/yo/dashboard")
        d = r.json()
        for key in ("usuario_email", "mis_glosas_abiertas",
                    "mis_vencidas", "mis_criticas",
                    "mis_menciones_pendientes", "cerradas_mes"):
            assert key in d

    def test_counts(self, client, db_session):
        _seed(db_session, dias_restantes=10)         # abierta normal
        _seed(db_session, dias_restantes=2)          # crítica
        _seed(db_session, dias_restantes=-5)         # vencida
        _seed(db_session, gestor="Bob")              # otro user

        r = client.get("/usuarios/yo/dashboard")
        d = r.json()
        assert d["mis_glosas_abiertas"] == 3
        assert d["mis_criticas"] == 1
        assert d["mis_vencidas"] == 1
