"""Tests del endpoint GET /glosas/stats/cargabilidad-equipo (R223 P1)."""
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


def _seed_n(db, gestor, n):
    for _ in range(n):
        db.add(GlosaRecord(
            eps="X", paciente="X", codigo_glosa="C",
            valor_objetado=1000, etapa="X", estado="RADICADA",
            creado_en=ahora_utc(),
            gestor_nombre=gestor,
        ))
    db.commit()


class TestCargabilidadEquipo:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/cargabilidad-equipo")
        d = r.json()
        for key in ("total_gestores_con_carga", "bandas"):
            assert key in d
        for k in ("ligera_1a5", "media_6a15",
                  "alta_16a30", "sobrecarga_mas_30"):
            assert k in d["bandas"]

    def test_clasificacion(self, client, db_session):
        _seed_n(db_session, "Light", 3)         # ligera
        _seed_n(db_session, "Medium", 10)       # media
        _seed_n(db_session, "High", 25)         # alta
        _seed_n(db_session, "Overload", 40)     # sobrecarga

        r = client.get("/glosas/stats/cargabilidad-equipo")
        d = r.json()
        assert d["bandas"]["ligera_1a5"] == 1
        assert d["bandas"]["media_6a15"] == 1
        assert d["bandas"]["alta_16a30"] == 1
        assert d["bandas"]["sobrecarga_mas_30"] == 1
