"""Tests del endpoint GET /glosas/{id}/playbook (R375 P1)."""
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


def _seed(db, gid, eps="X", codigo="C", estado="RADICADA",
          dictamen=None, dias=10, valor=1000):
    db.add(GlosaRecord(
        id=gid,
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dictamen=dictamen,
        dias_restantes=dias,
    ))
    db.commit()


class TestPlaybook:
    def test_alta_tasa_tono_conciliador(self, db_session, client):
        _seed(db_session, 1, dictamen="x" * 300)
        for i in range(3):
            _seed(db_session, 100 + i, estado="LEVANTADA")
        r = client.get("/glosas/1/playbook")
        d = r.json()
        assert d["tono_recomendado"] == "conciliador"
        assert d["tasa_par_pct"] == 100.0

    def test_baja_tasa_tono_firme(self, db_session, client):
        _seed(db_session, 1)
        for i in range(3):
            _seed(db_session, 100 + i, estado="RATIFICADA")
        r = client.get("/glosas/1/playbook")
        d = r.json()
        assert d["tono_recomendado"] == "firme"

    def test_riesgo_alto_si_vencida(self, db_session, client):
        _seed(db_session, 1, dias=-5, valor=15_000_000)
        r = client.get("/glosas/1/playbook")
        d = r.json()
        assert d["riesgo"]["nivel"] == "ALTO"
        assert "vencida" in d["riesgo"]["razones"]

    def test_404(self, client):
        r = client.get("/glosas/999/playbook")
        assert r.status_code == 404
