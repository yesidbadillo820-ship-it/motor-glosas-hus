"""Tests del endpoint GET /glosas/stats/heatmap-mes-eps (R275 P1)."""
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


def _seed(db, eps):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestHeatmapMesEPS:
    def test_top_eps_filtra(self, client, db_session):
        # SANITAS aparece 3 veces, otras 1 vez
        for _ in range(3):
            _seed(db_session, "SANITAS")
        _seed(db_session, "EPS001")
        _seed(db_session, "EPS002")

        r = client.get("/glosas/stats/heatmap-mes-eps?top_eps=2")
        d = r.json()
        assert "SANITAS" in d["eps"]
        assert len(d["eps"]) == 2
        # SANITAS debería tener count 3 en el mes actual
        mes_actual = d["meses"][0]
        assert d["matriz"]["SANITAS"][mes_actual] == 3

    def test_vacio(self, client):
        r = client.get("/glosas/stats/heatmap-mes-eps")
        d = r.json()
        assert d["meses"] == []
        assert d["eps"] == []
