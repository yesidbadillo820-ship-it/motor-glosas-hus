"""Tests del endpoint GET /glosas/stats/codigo-glosa-eps-cruzado (R305 P1)."""
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


def _seed(db, eps, codigo, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestCodigoEPSCruzado:
    def test_filtra_por_codigo(self, client, db_session):
        _seed(db_session, "SANITAS", "TA0801")
        _seed(db_session, "SANITAS", "TA0801")
        _seed(db_session, "EPS001", "TA0801", estado="RATIFICADA")
        _seed(db_session, "OTRA", "FA0603")

        r = client.get(
            "/glosas/stats/codigo-glosa-eps-cruzado?codigo=TA0801"
        )
        d = r.json()
        assert d["total_eps"] == 2
        sanitas = next(x for x in d["items"] if x["eps"] == "SANITAS")
        eps001 = next(x for x in d["items"] if x["eps"] == "EPS001")
        assert sanitas["levantadas"] == 2
        assert sanitas["tasa_levantamiento_pct"] == 100.0
        assert eps001["levantadas"] == 0
        assert eps001["tasa_levantamiento_pct"] == 0.0

    def test_codigo_inexistente(self, client):
        r = client.get(
            "/glosas/stats/codigo-glosa-eps-cruzado?codigo=ZZ"
        )
        d = r.json()
        assert d["items"] == []
