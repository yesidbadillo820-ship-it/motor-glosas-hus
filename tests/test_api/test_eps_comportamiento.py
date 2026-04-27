"""Tests del endpoint GET /glosas/{id}/eps-comportamiento (R374 P1)."""
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
    return UsuarioRecord(
        id=1, email="auditor@hus.com", rol="AUDITOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gid, eps="SAN", codigo="C", estado="RADICADA",
          dias_decision=None, codigo_respuesta=None):
    creado = ahora_utc()
    if dias_decision is not None:
        creado = creado - timedelta(days=dias_decision)
    db.add(GlosaRecord(
        id=gid,
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=creado,
        fecha_decision_eps=(
            ahora_utc() if dias_decision is not None else None
        ),
        codigo_respuesta=codigo_respuesta,
    ))
    db.commit()


class TestEPSComportamiento:
    def test_perfil_eps_conciliadora(self, db_session, client):
        # Glosa actual
        _seed(db_session, 1, eps="SAN")
        # Histórico SAN: 5 LEV / 5 dec → 100% (conciliadora)
        for i in range(5):
            _seed(
                db_session, 100 + i, eps="SAN", estado="LEVANTADA",
                dias_decision=10,
            )

        r = client.get("/glosas/1/eps-comportamiento")
        d = r.json()
        assert d["eps"] == "SAN"
        assert d["tasa_levantamiento_global_pct"] == 100.0
        assert "conciliadora" in d["estilo_resumen"].lower()

    def test_sin_eps(self, db_session, client):
        _seed(db_session, 1, eps="")
        r = client.get("/glosas/1/eps-comportamiento")
        d = r.json()
        assert d["estilo_resumen"] == "Sin EPS"

    def test_404(self, client):
        r = client.get("/glosas/999/eps-comportamiento")
        assert r.status_code == 404
