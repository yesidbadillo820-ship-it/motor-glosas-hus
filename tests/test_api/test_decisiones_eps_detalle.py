"""Tests del endpoint GET /glosas/stats/decisiones-eps-detalle (R221 P1)."""
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


def _seed(db, eps, estado):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=ahora_utc(),
    ))
    db.commit()


class TestDecisionesEPSDetalle:
    def test_eps_sin_decisiones(self, client):
        r = client.get(
            "/glosas/stats/decisiones-eps-detalle?eps=NO_EXISTE"
        )
        d = r.json()
        assert d["total_decididas"] == 0

    def test_distribucion_pct(self, client, db_session):
        # SANITAS: 6 LEVANTADA + 4 RATIFICADA = 60%/40%
        for _ in range(6):
            _seed(db_session, "SANITAS", "LEVANTADA")
        for _ in range(4):
            _seed(db_session, "SANITAS", "RATIFICADA")

        r = client.get(
            "/glosas/stats/decisiones-eps-detalle?eps=SANITAS"
        )
        d = r.json()
        items = {it["estado"]: it for it in d["items"]}
        assert items["LEVANTADA"]["pct"] == 60.0
        assert items["RATIFICADA"]["pct"] == 40.0

    def test_filtro_eps(self, client, db_session):
        _seed(db_session, "SANITAS", "LEVANTADA")
        _seed(db_session, "OTRA", "RATIFICADA")

        r = client.get(
            "/glosas/stats/decisiones-eps-detalle?eps=SANITAS"
        )
        d = r.json()
        assert d["total_decididas"] == 1
