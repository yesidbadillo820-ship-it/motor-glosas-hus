"""Tests del endpoint GET /usuarios/yo/dictamenes-stats (R348 P1)."""
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


def _seed(db, gestor, dictamen):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dictamen=dictamen,
    ))
    db.commit()


class TestYoDictamenesStats:
    def test_metricas(self, client, db_session):
        _seed(db_session, "Alice", "x" * 250)  # largo
        _seed(db_session, "Alice", "corto")    # corto (5 chars < 50)
        _seed(db_session, "Alice", "")         # sin dictamen
        _seed(db_session, "Bob", "no propia")  # otro

        r = client.get("/usuarios/yo/dictamenes-stats")
        d = r.json()
        assert d["count_total"] == 3
        assert d["count_con_dictamen"] == 2
        assert d["count_cortos"] == 2  # "corto" y ""
        assert d["count_largos"] == 1
