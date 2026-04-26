"""Tests del endpoint GET /usuarios/yo/glosas-grandes (R334 P1)."""
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


def _seed(db, gestor, valor, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestYoGlosasGrandes:
    def test_filtra_y_ordena(self, client, db_session):
        _seed(db_session, "Alice", valor=10_000_000)
        _seed(db_session, "Alice", valor=1_000_000)
        _seed(db_session, "Alice", valor=20_000_000, estado="LEVANTADA")
        _seed(db_session, "Bob", valor=99_999_999)

        r = client.get(
            "/usuarios/yo/glosas-grandes?umbral=5000000"
        )
        d = r.json()
        # Solo la primera (10M, abierta de Alice)
        assert d["total_grandes"] == 1
        assert d["items"][0]["valor_objetado"] == 10_000_000
