"""Tests del endpoint GET /usuarios/yo/glosas-criticas (R303 P1)."""
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


def _seed(db, gestor, dias_restantes, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias_restantes,
    ))
    db.commit()


class TestYoGlosasCriticas:
    def test_filtra_y_ordena(self, client, db_session):
        _seed(db_session, "Alice", dias_restantes=10)  # no crítica
        _seed(db_session, "Alice", dias_restantes=2)   # crítica
        _seed(db_session, "Alice", dias_restantes=-5)  # vencida
        _seed(db_session, "Bob", dias_restantes=0)     # no propia

        r = client.get("/usuarios/yo/glosas-criticas")
        d = r.json()
        assert d["total_criticas"] == 2
        assert d["vencidas"] == 1
        # Ordenado ASC: vencida primero
        assert d["items"][0]["dias_restantes"] == -5
        assert d["items"][0]["es_vencida"] is True

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, "Alice", dias_restantes=-1, estado="LEVANTADA")
        r = client.get("/usuarios/yo/glosas-criticas")
        d = r.json()
        assert d["total_criticas"] == 0
