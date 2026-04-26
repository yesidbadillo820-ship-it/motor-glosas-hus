"""Tests del endpoint GET /glosas/stats/progreso-equipo-mes (R320 P1)."""
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


def _seed(db, estado="RADICADA", valor=1000, recuperado=0,
          decidida=False):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=ahora_utc() if decidida else None,
    ))
    db.commit()


class TestProgresoEquipoMes:
    def test_metricas(self, client, db_session):
        _seed(db_session, estado="RADICADA")
        _seed(db_session, estado="LEVANTADA", recuperado=500,
              decidida=True)
        _seed(db_session, estado="RATIFICADA", decidida=True)

        r = client.get("/glosas/stats/progreso-equipo-mes")
        d = r.json()
        assert d["creadas_mes"] == 3
        assert d["cerradas_mes"] == 2
        assert d["levantadas_mes"] == 1
        assert d["valor_recuperado_mes"] == 500
        assert d["balance_neto"] == -1
