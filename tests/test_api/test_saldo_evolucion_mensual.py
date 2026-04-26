"""Tests del endpoint GET /glosas/stats/saldo-evolucion-mensual (R307 P1)."""
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


def _seed(db, dias_atras, saldo):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc() - timedelta(days=dias_atras),
        saldo_factura=saldo,
    ))
    db.commit()


class TestSaldoEvolucionMensual:
    def test_serie(self, client, db_session):
        _seed(db_session, dias_atras=5, saldo=10_000)
        _seed(db_session, dias_atras=5, saldo=5_000)

        r = client.get(
            "/glosas/stats/saldo-evolucion-mensual?meses=2"
        )
        d = r.json()
        assert len(d["serie"]) == 1
        mes = d["serie"][0]
        assert mes["glosas_creadas"] == 2
        assert mes["saldo_creado"] == 15_000

    def test_excluye_fuera_ventana(self, client, db_session):
        _seed(db_session, dias_atras=400, saldo=99_999)
        r = client.get(
            "/glosas/stats/saldo-evolucion-mensual?meses=2"
        )
        d = r.json()
        assert d["serie"] == []
