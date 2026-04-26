"""Tests del endpoint GET /glosas/stats/tipo-glosa-mensual (R289 P1)."""
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


def _seed(db, codigo):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestTipoGlosaMensual:
    def test_cuenta_por_prefijo(self, client, db_session):
        _seed(db_session, "TA0801")
        _seed(db_session, "TA0202")
        _seed(db_session, "SO0101")
        _seed(db_session, "FA0603")

        r = client.get("/glosas/stats/tipo-glosa-mensual?meses=2")
        d = r.json()
        assert "TA" in d["prefijos"]
        assert len(d["serie"]) == 1
        mes = d["serie"][0]
        assert mes["TA"] == 2
        assert mes["SO"] == 1
        assert mes["FA"] == 1

    def test_vacio(self, client):
        r = client.get("/glosas/stats/tipo-glosa-mensual")
        d = r.json()
        assert d["serie"] == []
