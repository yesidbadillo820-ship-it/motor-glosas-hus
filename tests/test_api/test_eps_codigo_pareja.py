"""Tests del endpoint GET /glosas/stats/eps-codigo-pareja (R252 P1)."""
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


def _seed(db, eps, codigo, estado):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestEPSCodigoPareja:
    def test_pareja_sin_historial(self, client):
        r = client.get(
            "/glosas/stats/eps-codigo-pareja?eps=XX&codigo_glosa=Y"
        )
        d = r.json()
        assert d["decididas"] == 0
        assert d["tasa_levantamiento_pct"] == 0.0

    def test_calcula_tasa(self, client, db_session):
        _seed(db_session, "SANITAS", "TA0201", "LEVANTADA")
        _seed(db_session, "SANITAS", "TA0201", "LEVANTADA")
        _seed(db_session, "SANITAS", "TA0201", "RATIFICADA")
        # 2/3 = 66.67%

        r = client.get(
            "/glosas/stats/eps-codigo-pareja"
            "?eps=SANITAS&codigo_glosa=TA0201"
        )
        d = r.json()
        assert d["levantadas"] == 2
        assert d["ratificadas"] == 1
        assert d["tasa_levantamiento_pct"] == 66.67
