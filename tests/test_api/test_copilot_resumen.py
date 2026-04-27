"""Tests del endpoint GET /sistema/copilot-resumen (R400 P1 — HITO)."""
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


def _seed(db, eps="X", gestor=None, dias=10, valor=1000,
          estado="RADICADA", recuperado=0, decidida=False):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
        fecha_decision_eps=ahora_utc() if decidida else None,
    ))
    db.commit()


class TestCopilotResumen:
    def test_estructura(self, client):
        r = client.get("/sistema/copilot-resumen")
        d = r.json()
        for k in (
            "frase_ejecutiva", "highlights", "kpis_resumen",
        ):
            assert k in d

    def test_frase_sin_vencidas(self, client, db_session):
        _seed(db_session, dias=10)
        r = client.get("/sistema/copilot-resumen")
        d = r.json()
        # Sin vencidas → mensaje positivo
        assert "✅" in d["frase_ejecutiva"] or "📋" in d["frase_ejecutiva"]

    def test_alerta_grandes_vencidas(self, client, db_session):
        for _ in range(6):
            _seed(db_session, dias=-3, valor=10_000_000)
        r = client.get("/sistema/copilot-resumen")
        d = r.json()
        assert "⚠️" in d["frase_ejecutiva"]
        assert d["kpis_resumen"]["vencidas_grandes"] >= 5
