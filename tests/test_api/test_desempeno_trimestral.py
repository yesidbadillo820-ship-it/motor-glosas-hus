"""Tests del endpoint GET /glosas/stats/desempeno-trimestral (R109 P1)."""
from __future__ import annotations

from datetime import datetime, timezone

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


def _seed(db, fecha, estado="RADICADA", valor_obj=1000, valor_rec=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor_obj, valor_recuperado=valor_rec,
        etapa="X", estado=estado, creado_en=fecha,
    ))
    db.commit()


class TestDesempenoTrimestral:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/desempeno-trimestral")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["serie"] == []

    def test_agrupa_por_trimestre(self, client, db_session):
        # Q2 2026: abril, mayo, junio
        _seed(db_session, datetime(2026, 4, 5, tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 5, 1, tzinfo=timezone.utc))
        # Q1 2026: ene, feb, mar
        _seed(db_session, datetime(2026, 2, 15, tzinfo=timezone.utc))

        r = client.get("/glosas/stats/desempeno-trimestral")
        d = r.json()
        trims = {s["trimestre"]: s for s in d["serie"]}
        assert "2026-Q2" in trims
        assert trims["2026-Q2"]["total_glosas"] == 2
        assert trims["2026-Q1"]["total_glosas"] == 1

    def test_metricas_trimestre(self, client, db_session):
        fecha = datetime(2026, 4, 5, tzinfo=timezone.utc)
        _seed(db_session, fecha, "LEVANTADA",
              valor_obj=10000, valor_rec=10000)
        _seed(db_session, fecha, "ACEPTADA",
              valor_obj=5000, valor_rec=0)
        _seed(db_session, fecha, "RADICADA")

        r = client.get("/glosas/stats/desempeno-trimestral")
        d = r.json()
        item = next(s for s in d["serie"] if s["trimestre"] == "2026-Q2")
        assert item["total_glosas"] == 3
        assert item["decididas"] == 2
        assert item["pendientes"] == 1
        assert item["levantadas"] == 1
        # 1/2 = 50%
        assert item["tasa_levantamiento_pct"] == 50.0
        # 10000/16000 = 62.5%
        assert item["tasa_recuperacion_pct"] == 62.5

    def test_orden_ascendente(self, client, db_session):
        _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 1, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2025, 12, 1, tzinfo=timezone.utc))
        r = client.get("/glosas/stats/desempeno-trimestral")
        d = r.json()
        trims = [s["trimestre"] for s in d["serie"]]
        assert trims == sorted(trims)

    def test_limita_trimestres(self, client, db_session):
        # 5 trimestres distintos
        for mes in [3, 6, 9, 12, 3]:
            year = 2025 if mes != 3 or len([m for m in [3, 6, 9, 12, 3] if m == 3]) > 1 else 2026
            _seed(db_session, datetime(year, mes, 1, tzinfo=timezone.utc))
        # Pedir solo 2
        r = client.get("/glosas/stats/desempeno-trimestral?trimestres=2")
        d = r.json()
        assert len(d["serie"]) <= 2
