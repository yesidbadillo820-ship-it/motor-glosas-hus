"""Tests del endpoint GET /glosas/stats/devoluciones-resumen (R317 P1)."""
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


def _seed(db, eps, devolucion=None, estado="RADICADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        es_devolucion=devolucion,
    ))
    db.commit()


class TestDevolucionesResumen:
    def test_filtra_devoluciones(self, client, db_session):
        _seed(db_session, "X", devolucion="1")
        _seed(db_session, "Y", devolucion="S")
        _seed(db_session, "Z", devolucion=None)  # no devolucion

        r = client.get("/glosas/stats/devoluciones-resumen")
        d = r.json()
        assert d["count_total_devoluciones"] == 2

    def test_top_eps(self, client, db_session):
        for _ in range(3):
            _seed(db_session, "SANITAS", devolucion="1")
        _seed(db_session, "OTRA", devolucion="1")

        r = client.get("/glosas/stats/devoluciones-resumen")
        d = r.json()
        assert d["top_eps"][0]["eps"] == "SANITAS"
        assert d["top_eps"][0]["count"] == 3

    def test_abiertas_vs_cerradas(self, client, db_session):
        _seed(db_session, "X", devolucion="1", estado="RADICADA")
        _seed(
            db_session, "X", devolucion="1", estado="LEVANTADA",
        )
        r = client.get("/glosas/stats/devoluciones-resumen")
        d = r.json()
        assert d["count_abiertas"] == 1
        assert d["count_cerradas"] == 1
