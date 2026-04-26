"""Tests del endpoint GET /glosas/stats/cerradas-por-etapa (R173 P1)."""
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


def _seed(db, etapa, estado="LEVANTADA", valor_rec=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_recuperado=valor_rec,
        etapa=etapa, estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestCerradasPorEtapa:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/cerradas-por-etapa")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_excluye_abiertas(self, client, db_session):
        _seed(db_session, "RESPUESTA_PRIMERA", estado="RADICADA")
        r = client.get("/glosas/stats/cerradas-por-etapa")
        d = r.json()
        assert d["items"] == []

    def test_distribucion_y_tasa(self, client, db_session):
        # PRIMERA: 2 LEVANTADA + 1 ACEPTADA = 66.67% lev
        _seed(db_session, "PRIMERA", estado="LEVANTADA",
              valor_rec=5000)
        _seed(db_session, "PRIMERA", estado="LEVANTADA",
              valor_rec=3000)
        _seed(db_session, "PRIMERA", estado="ACEPTADA",
              valor_rec=0)
        # CONCILIACION: 1 CONCILIADA
        _seed(db_session, "CONCILIACION", estado="CONCILIADA",
              valor_rec=1000)

        r = client.get("/glosas/stats/cerradas-por-etapa")
        d = r.json()
        items = {it["etapa"]: it for it in d["items"]}
        assert items["PRIMERA"]["count"] == 3
        assert items["PRIMERA"]["valor_recuperado_total"] == 8000
        assert items["PRIMERA"]["tasa_levantamiento_pct"] == 66.67
        assert items["CONCILIACION"]["count"] == 1
        assert d["total_glosas_cerradas"] == 4
