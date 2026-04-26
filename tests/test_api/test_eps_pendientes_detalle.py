"""Tests del endpoint GET /glosas/stats/eps-pendientes-detalle (R243 P1)."""
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


def _seed(db, eps, dr=10, estado="RADICADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dias_restantes=dr,
    ))
    db.commit()


class TestEPSPendientesDetalle:
    def test_orden_y_vencidas(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "GRANDE")
        for _ in range(2):
            _seed(db_session, "GRANDE", dr=-5)  # vencidas
        for _ in range(3):
            _seed(db_session, "MEDIANA")

        r = client.get("/glosas/stats/eps-pendientes-detalle")
        d = r.json()
        items = {it["eps"]: it for it in d["items"]}
        assert items["GRANDE"]["count_pendientes"] == 7
        assert items["GRANDE"]["vencidas"] == 2
        assert items["MEDIANA"]["count_pendientes"] == 3

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, "X", estado="LEVANTADA")
        r = client.get("/glosas/stats/eps-pendientes-detalle")
        d = r.json()
        assert d["items"] == []
