"""Tests del endpoint GET /glosas/stats/cups-sin-tarifa (R170 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ConceptoGlosaRecord, GlosaRecord,
    TarifaContratadaRecord, UsuarioRecord,
)


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


def _seed_glosa(db, gid, eps):
    db.add(GlosaRecord(
        id=gid, eps=eps, paciente="X", codigo_glosa="TA",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_concepto(db, gid, cups, valor=1000):
    db.add(ConceptoGlosaRecord(
        glosa_id=gid, codigo_glosa="TA0201",
        cups_codigo=cups, valor_objetado=valor,
    ))
    db.commit()


def _seed_tarifa(db, eps, cups):
    db.add(TarifaContratadaRecord(
        eps=eps, codigo_cups=cups, valor_pactado=1000,
    ))
    db.commit()


class TestCupsSinTarifa:
    def test_eps_sin_glosas(self, client):
        r = client.get(
            "/glosas/stats/cups-sin-tarifa?eps=Inexistente"
        )
        d = r.json()
        assert d["items"] == []

    def test_detecta_cups_sin_tarifa(self, client, db_session):
        _seed_glosa(db_session, 1, "SANITAS")
        _seed_concepto(db_session, 1, "111")  # SIN tarifa
        _seed_concepto(db_session, 1, "222")  # CON tarifa
        _seed_tarifa(db_session, "SANITAS", "222")

        r = client.get("/glosas/stats/cups-sin-tarifa?eps=SANITAS")
        d = r.json()
        cups = [it["cups_codigo"] for it in d["items"]]
        assert "111" in cups
        assert "222" not in cups

    def test_orden_por_frecuencia(self, client, db_session):
        _seed_glosa(db_session, 1, "XX")
        _seed_concepto(db_session, 1, "AAA")
        _seed_concepto(db_session, 1, "AAA")
        _seed_concepto(db_session, 1, "AAA")
        _seed_concepto(db_session, 1, "BBB")

        r = client.get("/glosas/stats/cups-sin-tarifa?eps=XX")
        d = r.json()
        assert d["items"][0]["cups_codigo"] == "AAA"
        assert d["items"][0]["frecuencia"] == 3

    def test_aislamiento_por_eps(self, client, db_session):
        _seed_glosa(db_session, 1, "SANITAS")
        _seed_glosa(db_session, 2, "OTRA_EPS")
        _seed_concepto(db_session, 1, "111")
        _seed_concepto(db_session, 2, "999")

        r = client.get("/glosas/stats/cups-sin-tarifa?eps=SANITAS")
        d = r.json()
        cups = [it["cups_codigo"] for it in d["items"]]
        assert cups == ["111"]
