"""Tests del endpoint GET /glosas/stats/eps-codigo-rentabilidad (R352 P1)."""
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


def _seed(db, eps, codigo, recuperado, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestEPSCodigoRentabilidad:
    def test_calcula(self, client, db_session):
        _seed(db_session, "X", "TA01", recuperado=1000)
        _seed(db_session, "X", "TA01", recuperado=3000)
        # 2 dec, 4000 total, 2000 promedio

        r = client.get(
            "/glosas/stats/eps-codigo-rentabilidad?min_decididas=1"
        )
        d = r.json()
        item = d["items"][0]
        assert item["eps"] == "X"
        assert item["codigo_glosa"] == "TA01"
        assert item["valor_recuperado_total"] == 4000
        assert item["valor_recuperado_promedio"] == 2000
