"""Tests del endpoint GET /glosas/{id}/probabilidad-levantamiento (R299 P1)."""
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


def _seed(db, glosa_id, eps, codigo, estado="RADICADA", gestor=None):
    db.add(GlosaRecord(
        id=glosa_id,
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestProbabilidadLevantamiento:
    def test_calcula_combinado(self, client, db_session):
        # Glosa actual: par (SANITAS, TA0801), gestor Alice
        _seed(
            db_session, 1, "SANITAS", "TA0801",
            estado="RADICADA", gestor="Alice",
        )
        # Histórico par (SANITAS, TA0801): 2 LEV / 2 dec → 100%
        _seed(db_session, 2, "SANITAS", "TA0801", estado="LEVANTADA")
        _seed(db_session, 3, "SANITAS", "TA0801", estado="LEVANTADA")
        # Histórico gestor Alice: 1 LEV / 2 dec → 50%
        _seed(db_session, 4, "OTRA", "X", estado="LEVANTADA",
              gestor="Alice")
        _seed(db_session, 5, "OTRA", "X", estado="RATIFICADA",
              gestor="Alice")

        r = client.get("/glosas/1/probabilidad-levantamiento")
        d = r.json()
        assert d["tasa_par_eps_codigo_pct"] == 100.0
        assert d["tasa_gestor_pct"] == 50.0
        # 100*0.6 + 50*0.4 = 80
        assert d["probabilidad_levantamiento_pct"] == 80.0

    def test_sin_historial(self, client, db_session):
        _seed(db_session, 1, "X", "X", estado="RADICADA")
        r = client.get("/glosas/1/probabilidad-levantamiento")
        d = r.json()
        assert d["probabilidad_levantamiento_pct"] is None
        assert d["n_par"] == 0

    def test_404(self, client):
        r = client.get("/glosas/999/probabilidad-levantamiento")
        assert r.status_code == 404
