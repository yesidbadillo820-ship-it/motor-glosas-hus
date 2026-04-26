"""Tests del endpoint GET /glosas/stats/anomalias (R114 P1)."""
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


def _seed(db, valor):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestAnomalias:
    def test_pocos_datos(self, client, db_session):
        _seed(db_session, 100)
        _seed(db_session, 200)
        r = client.get("/glosas/stats/anomalias")
        d = r.json()
        # Necesita >=4 para cuartiles
        assert "razon" in d

    def test_detecta_outlier_alto(self, client, db_session):
        # Cluster normal alrededor de 1000
        for _ in range(10):
            _seed(db_session, 1000)
        # Outlier alto extremo
        _seed(db_session, 1_000_000)
        r = client.get("/glosas/stats/anomalias")
        d = r.json()
        assert d["total_outliers_altos"] == 1
        assert d["outliers_altos"][0]["valor_objetado"] == 1_000_000

    def test_estadisticas(self, client, db_session):
        for _ in range(10):
            _seed(db_session, 1000)
        _seed(db_session, 1_000_000)
        r = client.get("/glosas/stats/anomalias")
        d = r.json()
        stats = d["estadisticas"]
        assert "q1" in stats
        assert "q3" in stats
        assert "iqr" in stats
        assert "limite_superior_outlier" in stats

    def test_sin_outliers(self, client, db_session):
        # Distribución compacta, no hay outliers
        for v in [100, 200, 300, 400, 500, 600]:
            _seed(db_session, v)
        r = client.get("/glosas/stats/anomalias")
        d = r.json()
        assert d["total_outliers_altos"] == 0

    def test_outliers_altos_ordenados_desc(self, client, db_session):
        for _ in range(10):
            _seed(db_session, 1000)
        # 3 outliers altos
        _seed(db_session, 100_000)
        _seed(db_session, 500_000)
        _seed(db_session, 200_000)
        r = client.get("/glosas/stats/anomalias")
        d = r.json()
        valores = [it["valor_objetado"] for it in d["outliers_altos"]]
        assert valores == sorted(valores, reverse=True)
