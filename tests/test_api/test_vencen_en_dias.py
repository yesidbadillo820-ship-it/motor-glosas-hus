"""Tests del endpoint GET /glosas/stats/vencen-en-dias (R342 P1)."""
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
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, dias_restantes, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dias_restantes=dias_restantes,
    ))
    db.commit()


class TestVencenEnDias:
    def test_filtra_y_ordena(self, client, db_session):
        _seed(db_session, dias_restantes=2)
        _seed(db_session, dias_restantes=5)
        _seed(db_session, dias_restantes=10)  # fuera ventana 7
        _seed(db_session, dias_restantes=-1)  # vencida, no incluida

        r = client.get("/glosas/stats/vencen-en-dias?dias=7")
        d = r.json()
        assert d["total_proximos_a_vencer"] == 2
        # Ascending
        assert d["items"][0]["dias_restantes"] == 2

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, dias_restantes=3, estado="LEVANTADA")
        r = client.get("/glosas/stats/vencen-en-dias?dias=7")
        d = r.json()
        assert d["total_proximos_a_vencer"] == 0
