"""Tests del endpoint GET /glosas/stats/eps-respuestas-codigos (R274 P1)."""
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


def _seed(db, eps, codigo_respuesta, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        codigo_respuesta=codigo_respuesta,
    ))
    db.commit()


class TestEPSRespuestasCodigos:
    def test_filtra_por_eps(self, client, db_session):
        _seed(db_session, "SANITAS", "RE9501")
        _seed(db_session, "OTRA", "RE9701")
        r = client.get(
            "/glosas/stats/eps-respuestas-codigos?eps=SANITAS"
        )
        d = r.json()
        assert d["eps"] == "SANITAS"
        assert d["total_codigos"] == 1
        assert d["items"][0]["codigo_respuesta"] == "RE9501"

    def test_tasa(self, client, db_session):
        _seed(db_session, "XX", "RE9501", estado="LEVANTADA")
        _seed(db_session, "XX", "RE9501", estado="LEVANTADA")
        _seed(db_session, "XX", "RE9501", estado="RATIFICADA")
        # 2/3 ≈ 66.67%
        r = client.get(
            "/glosas/stats/eps-respuestas-codigos?eps=XX"
        )
        d = r.json()
        item = d["items"][0]
        assert item["count_total"] == 3
        assert item["levantadas"] == 2
        assert item["ratificadas"] == 1
        assert item["tasa_levantamiento_pct"] == 66.67

    def test_excluye_sin_codigo(self, client, db_session):
        _seed(db_session, "XX", None)
        _seed(db_session, "XX", "")
        r = client.get(
            "/glosas/stats/eps-respuestas-codigos?eps=XX"
        )
        d = r.json()
        assert d["items"] == []
