"""Tests del endpoint GET /glosas/stats/distribucion-valores (R89 P2)."""
from __future__ import annotations

from datetime import timedelta

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


def _seed(db, valor, dias_atras=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestDistribucionValores:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/distribucion-valores")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_glosas"] == 0
        assert d["valor_total"] == 0
        assert d["valor_promedio"] == 0.0
        assert d["valor_mediano"] == 0.0
        # Todos los buckets presentes con count=0
        assert len(d["buckets"]) == 7
        assert all(b["count"] == 0 for b in d["buckets"])

    def test_buckets_correctos(self, client, db_session):
        _seed(db_session, 50_000)        # <100k
        _seed(db_session, 250_000)       # 100k-500k
        _seed(db_session, 750_000)       # 500k-1M
        _seed(db_session, 3_000_000)     # 1M-5M
        _seed(db_session, 7_000_000)     # 5M-10M
        _seed(db_session, 25_000_000)    # 10M-50M
        _seed(db_session, 100_000_000)   # 50M+

        r = client.get("/glosas/stats/distribucion-valores")
        d = r.json()
        assert d["total_glosas"] == 7
        # Cada bucket debe tener exactamente 1
        counts = {b["rango"]: b["count"] for b in d["buckets"]}
        assert counts == {
            "<100k": 1, "100k-500k": 1, "500k-1M": 1,
            "1M-5M": 1, "5M-10M": 1, "10M-50M": 1, "50M+": 1,
        }

    def test_estadisticas_basicas(self, client, db_session):
        _seed(db_session, 100)
        _seed(db_session, 200)
        _seed(db_session, 300)
        r = client.get("/glosas/stats/distribucion-valores")
        d = r.json()
        assert d["total_glosas"] == 3
        assert d["valor_total"] == 600
        assert d["valor_promedio"] == 200.0
        assert d["valor_mediano"] == 200.0  # mediana = el del medio

    def test_mediana_par(self, client, db_session):
        _seed(db_session, 100)
        _seed(db_session, 200)
        _seed(db_session, 300)
        _seed(db_session, 400)
        r = client.get("/glosas/stats/distribucion-valores")
        d = r.json()
        # 4 elementos → mediana = (200+300)/2 = 250
        assert d["valor_mediano"] == 250.0

    def test_pct_count_y_pct_valor(self, client, db_session):
        # 9 glosas <100k (50k cada una = 450k total)
        for _ in range(9):
            _seed(db_session, 50_000)
        # 1 glosa 50M+ (60M)
        _seed(db_session, 60_000_000)

        r = client.get("/glosas/stats/distribucion-valores")
        d = r.json()
        bucket_chico = next(b for b in d["buckets"] if b["rango"] == "<100k")
        bucket_50m = next(b for b in d["buckets"] if b["rango"] == "50M+")

        # 9/10 = 90% del count, pero solo 450k / (450k+60M) ≈ 0.74%
        assert bucket_chico["pct_count"] == 90.0
        assert bucket_chico["pct_valor"] < 1.0
        # Inverso: 1 sola glosa pero domina el valor
        assert bucket_50m["pct_count"] == 10.0
        assert bucket_50m["pct_valor"] > 99.0

    def test_excluye_fuera_de_ventana(self, client, db_session):
        _seed(db_session, 100, dias_atras=10)    # dentro
        _seed(db_session, 200, dias_atras=400)   # fuera (default 180d)
        r = client.get("/glosas/stats/distribucion-valores")
        d = r.json()
        assert d["total_glosas"] == 1
        assert d["valor_total"] == 100
