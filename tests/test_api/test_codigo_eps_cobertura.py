"""Tests del endpoint GET /glosas/stats/codigo-eps-cobertura (R332 P1)."""
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


class TestCodigoEPSCobertura:
    def test_universal_vs_nicho(self, client, db_session):
        # TA0801 usado por 3 EPS distintas
        _seed(db_session, "SANITAS", "TA0801")
        _seed(db_session, "EPS001", "TA0801")
        _seed(db_session, "OTRA", "TA0801")
        # FA0603 usado por 1 EPS
        _seed(db_session, "SANITAS", "FA0603")

        r = client.get(
            "/glosas/stats/codigo-eps-cobertura?min_glosas=1"
        )
        d = r.json()
        ta = next(x for x in d["items"] if x["codigo_glosa"] == "TA0801")
        fa = next(x for x in d["items"] if x["codigo_glosa"] == "FA0603")
        assert ta["eps_distintas"] == 3
        assert fa["eps_distintas"] == 1
        # Ordenado DESC por eps_distintas
        assert d["items"][0]["codigo_glosa"] == "TA0801"
