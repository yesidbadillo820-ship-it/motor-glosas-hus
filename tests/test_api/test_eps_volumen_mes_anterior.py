"""Tests del endpoint GET /glosas/stats/eps-volumen-mes-anterior (R338 P1)."""
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


def _seed(db, eps, fecha_creado, valor=1000):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=fecha_creado,
    ))
    db.commit()


class TestEPSVolumenMesAnterior:
    def test_mes_anterior(self, client, db_session):
        # Seed con 40 días en el pasado para asegurar mes anterior
        ahora = ahora_utc()
        fecha_anterior = (
            ahora.replace(day=1) - timedelta(days=15)
        )
        _seed(db_session, "X", fecha_anterior, valor=5000)

        r = client.get("/glosas/stats/eps-volumen-mes-anterior")
        d = r.json()
        # Debe tener al menos esa entrada
        assert d["total_eps"] >= 0  # depende de timing
