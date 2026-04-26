"""Tests del endpoint GET /glosas/stats/distribucion-urgencia (R219 P1)."""
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


def _seed(db, dr, valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        dias_restantes=dr,
    ))
    db.commit()


class TestDistribucionUrgencia:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/distribucion-urgencia")
        d = r.json()
        # 4 bandas siempre
        assert len(d["items"]) == 4

    def test_clasificacion(self, client, db_session):
        _seed(db_session, dr=-5)
        _seed(db_session, dr=2)
        _seed(db_session, dr=5)
        _seed(db_session, dr=20)

        r = client.get("/glosas/stats/distribucion-urgencia")
        d = r.json()
        items = {it["banda"]: it for it in d["items"]}
        assert items["VENCIDA"]["count"] == 1
        assert items["CRITICA"]["count"] == 1
        assert items["PROXIMA"]["count"] == 1
        assert items["LEJANA"]["count"] == 1

    def test_pct_consistente(self, client, db_session):
        for _ in range(8):
            _seed(db_session, dr=20)  # LEJANA
        for _ in range(2):
            _seed(db_session, dr=-1)  # VENCIDA
        r = client.get("/glosas/stats/distribucion-urgencia")
        d = r.json()
        items = {it["banda"]: it for it in d["items"]}
        # 80% LEJANA, 20% VENCIDA
        assert items["LEJANA"]["pct"] == 80.0
        assert items["VENCIDA"]["pct"] == 20.0
