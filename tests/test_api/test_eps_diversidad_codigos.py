"""Tests del endpoint GET /glosas/stats/eps-diversidad-codigos (R293 P1)."""
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


def _seed(db, eps, codigo):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestEPSDiversidadCodigos:
    def test_diversidad(self, client, db_session):
        # SANITAS: 3 glosas con 3 códigos distintos → diverso
        _seed(db_session, "SANITAS", "TA0801")
        _seed(db_session, "SANITAS", "FA0603")
        _seed(db_session, "SANITAS", "SO0101")
        # OTRA: 3 glosas con 1 código → especializada
        _seed(db_session, "OTRA", "TA0801")
        _seed(db_session, "OTRA", "TA0801")
        _seed(db_session, "OTRA", "TA0801")

        r = client.get(
            "/glosas/stats/eps-diversidad-codigos?min_glosas=1"
        )
        d = r.json()
        sanitas = next(x for x in d["items"] if x["eps"] == "SANITAS")
        otra = next(x for x in d["items"] if x["eps"] == "OTRA")
        assert sanitas["codigos_distintos"] == 3
        assert sanitas["ratio_diversidad"] == 1.0
        assert otra["codigos_distintos"] == 1
        assert otra["ratio_diversidad"] == round(1 / 3, 3)

    def test_min_glosas_filtra(self, client, db_session):
        _seed(db_session, "POCAS", "X")
        r = client.get(
            "/glosas/stats/eps-diversidad-codigos?min_glosas=5"
        )
        d = r.json()
        assert d["items"] == []
