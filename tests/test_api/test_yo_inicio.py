"""Tests del endpoint GET /usuarios/yo/inicio (R378 P1)."""
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
        id=1, email="alice@hus.com", nombre="Alice",
        rol="AUDITOR", activo=1,
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


def _seed(db, gestor="Alice", dias=10, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
    ))
    db.commit()


class TestYoInicio:
    def test_estructura(self, client):
        r = client.get("/usuarios/yo/inicio")
        d = r.json()
        for k in (
            "saludo_hora", "resumen_dia", "top_acciones",
            "top_quick_wins", "menciones_pendientes",
        ):
            assert k in d

    def test_resumen_dia(self, client, db_session):
        _seed(db_session, dias=-5)  # vencida
        _seed(db_session, dias=2)   # crítica
        _seed(db_session, dias=10)  # normal
        r = client.get("/usuarios/yo/inicio")
        d = r.json()
        assert d["resumen_dia"]["abiertas"] == 3
        assert d["resumen_dia"]["vencidas"] == 1
        assert d["resumen_dia"]["criticas"] == 1
