"""Tests del endpoint GET /glosas/stats/anomalias-valor (R233 P1)."""
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


def _seed(db, valor, eps="X", codigo="C"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestAnomaliasValor:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/anomalias-valor")
        d = r.json()
        for key in ("factor_z_filtro", "total_anomalias", "items"):
            assert key in d

    def test_detecta_outlier(self, client, db_session):
        # 5 valores normales (1000) + 1 outlier (1M)
        for _ in range(5):
            _seed(db_session, 1000)
        _seed(db_session, 1_000_000)

        r = client.get("/glosas/stats/anomalias-valor?factor_z=2")
        d = r.json()
        # El outlier debe aparecer
        assert d["total_anomalias"] >= 1

    def test_cohorte_pequena_excluida(self, client, db_session):
        # Solo 3 glosas → cohorte <5, no se evalúa
        _seed(db_session, 1000)
        _seed(db_session, 1000)
        _seed(db_session, 999_999)
        r = client.get("/glosas/stats/anomalias-valor?factor_z=2")
        d = r.json()
        assert d["items"] == []
