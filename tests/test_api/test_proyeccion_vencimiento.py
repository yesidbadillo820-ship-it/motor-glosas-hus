"""Tests del endpoint GET /glosas/stats/proyeccion-vencimiento (R178 P1)."""
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


def _seed(db, dr, valor=1000, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dias_restantes=dr,
    ))
    db.commit()


class TestProyeccionVencimiento:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/proyeccion-vencimiento")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "total_glosas_proximas",
                    "valor_total_proximas", "serie"):
            assert key in d

    def test_excluye_vencidas_y_lejanas(self, client, db_session):
        _seed(db_session, dr=-5)  # vencida → no
        _seed(db_session, dr=15)  # dentro de 30 → sí
        _seed(db_session, dr=50)  # fuera de 30 → no

        r = client.get("/glosas/stats/proyeccion-vencimiento")
        d = r.json()
        assert d["total_glosas_proximas"] == 1

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, dr=10, estado="LEVANTADA")
        r = client.get("/glosas/stats/proyeccion-vencimiento")
        d = r.json()
        assert d["serie"] == []

    def test_serie_ascendente(self, client, db_session):
        _seed(db_session, dr=10)
        _seed(db_session, dr=2)
        _seed(db_session, dr=5)
        r = client.get("/glosas/stats/proyeccion-vencimiento")
        d = r.json()
        dias = [s["dias_restantes"] for s in d["serie"]]
        assert dias == [2, 5, 10]
