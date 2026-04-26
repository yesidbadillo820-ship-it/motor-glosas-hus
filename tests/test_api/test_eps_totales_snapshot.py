"""Tests del endpoint GET /glosas/stats/eps-totales-snapshot (R331 P1)."""
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


def _seed(db, eps, estado="RADICADA", valor=1000, recuperado=0,
          saldo=0):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        saldo_factura=saldo,
    ))
    db.commit()


class TestEPSTotalesSnapshot:
    def test_metricas(self, client, db_session):
        _seed(
            db_session, "X", estado="LEVANTADA",
            valor=1000, recuperado=800,
        )
        _seed(
            db_session, "X", estado="RADICADA",
            valor=2000, saldo=2000,
        )
        # 1/2 LEV → tasa 100% sobre 1 decidida

        r = client.get("/glosas/stats/eps-totales-snapshot")
        d = r.json()
        item = next(x for x in d["items"] if x["eps"] == "X")
        assert item["count_total"] == 2
        assert item["count_abiertas"] == 1
        assert item["valor_objetado_total"] == 3000
        assert item["valor_recuperado_total"] == 800
        assert item["saldo_total"] == 2000
        assert item["tasa_levantamiento_pct"] == 100.0
