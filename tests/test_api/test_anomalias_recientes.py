"""Tests del endpoint GET /glosas/stats/anomalias-recientes (R388 P1)."""
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
    return UsuarioRecord(id=1, email="x@x", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, eps, dias_atras, codigo="C"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestAnomaliasRecientes:
    def test_pico(self, client, db_session):
        # Histórico: 1 por semana en últimas 12 semanas
        for i in range(1, 13):
            _seed(db_session, "X", dias_atras=i * 7 + 1)
        # Esta semana: 10 (10x el promedio)
        for _ in range(10):
            _seed(db_session, "X", dias_atras=2)
        r = client.get("/glosas/stats/anomalias-recientes")
        d = r.json()
        picos = [x for x in d["items"] if x["tipo"] == "PICO"]
        assert any(p["eps"] == "X" for p in picos)

    def test_codigo_nuevo(self, client, db_session):
        # Esta semana: 3 con código nuevo en EPS sin histórico
        for _ in range(3):
            _seed(db_session, "Y", dias_atras=1, codigo="NUEVO123")
        r = client.get("/glosas/stats/anomalias-recientes")
        d = r.json()
        nuevos = [x for x in d["items"] if x["tipo"] == "NUEVO_CODIGO"]
        assert any(
            n.get("codigo_glosa") == "NUEVO123" for n in nuevos
        )

    def test_estructura(self, client):
        r = client.get("/glosas/stats/anomalias-recientes")
        assert r.status_code == 200
