"""Tests del endpoint GET /glosas/stats/codigos-recuperacion-monetaria (R339 P1)."""
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


def _seed(db, codigo, obj, rec, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa=codigo,
        valor_objetado=obj, valor_recuperado=rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestCodigosRecuperacionMonetaria:
    def test_calcula(self, client, db_session):
        _seed(db_session, "TA0801", 1000, 800)
        _seed(db_session, "TA0801", 2000, 1200)
        # Ratio: 2000/3000 = 66.67%

        r = client.get(
            "/glosas/stats/codigos-recuperacion-monetaria?min_glosas=1"
        )
        d = r.json()
        item = d["items"][0]
        assert item["codigo_glosa"] == "TA0801"
        assert item["valor_objetado_total"] == 3000
        assert item["valor_recuperado_total"] == 2000
        assert item["tasa_recuperacion_monetaria_pct"] == 66.67
