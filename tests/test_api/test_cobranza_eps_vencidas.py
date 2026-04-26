"""Tests del endpoint GET /glosas/stats/cobranza-eps-vencidas (R364 P1)."""
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


def _seed(db, eps, dias, estado="RADICADA", valor=1000, saldo=500):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dias_restantes=dias,
        saldo_factura=saldo,
    ))
    db.commit()


class TestCobranzaEPSVencidas:
    def test_filtra_y_promedio(self, client, db_session):
        _seed(db_session, "X", -5, valor=1000, saldo=500)
        _seed(db_session, "X", -10, valor=2000, saldo=1500)
        # No vencida, no cuenta
        _seed(db_session, "X", 5, valor=999)

        r = client.get("/glosas/stats/cobranza-eps-vencidas")
        d = r.json()
        item = d["items"][0]
        assert item["eps"] == "X"
        assert item["count_vencidas"] == 2
        assert item["dias_promedio_vencido"] == 7.5
        assert item["valor_objetado_total"] == 3000
        assert item["saldo_total"] == 2000
