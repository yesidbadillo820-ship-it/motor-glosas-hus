"""Tests del endpoint GET /glosas/stats/tiempo-primer-dictamen (R226 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import DictamenVersionRecord, GlosaRecord, UsuarioRecord


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


def _seed_pair(db, gid, horas_para_dictamen):
    cre = ahora_utc() - timedelta(days=10)
    prim = cre + timedelta(hours=horas_para_dictamen)
    db.add(GlosaRecord(
        id=gid, eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=cre,
    ))
    db.commit()
    db.add(DictamenVersionRecord(
        glosa_id=gid, dictamen_html="x",
        accion="CREAR", creado_en=prim,
    ))
    db.commit()


class TestTiempoPrimerDictamen:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/tiempo-primer-dictamen")
        d = r.json()
        for key in ("count_glosas_evaluadas",
                    "tiempo_promedio_horas",
                    "tiempo_mediano_horas",
                    "tiempo_max_horas"):
            assert key in d

    def test_promedio(self, client, db_session):
        _seed_pair(db_session, 1, horas_para_dictamen=2)
        _seed_pair(db_session, 2, horas_para_dictamen=4)
        _seed_pair(db_session, 3, horas_para_dictamen=6)
        # promedio = 4 horas

        r = client.get("/glosas/stats/tiempo-primer-dictamen")
        d = r.json()
        assert d["count_glosas_evaluadas"] == 3
        assert d["tiempo_promedio_horas"] == 4.0
        assert d["tiempo_mediano_horas"] == 4.0
        assert d["tiempo_max_horas"] == 6.0
