"""Tests del endpoint GET /glosas/stats/tarifa-coincidente (R169 P1)."""
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


def _seed_concepto(db, gid, codigo_glosa="TA0201", cups="906625"):
    db.add(ConceptoGlosaRecord(
        glosa_id=gid, codigo_glosa=codigo_glosa,
        cups_codigo=cups, valor_objetado=500,
    ))
    db.commit()


def _seed_tarifa(db, eps, cups):
    db.add(TarifaContratadaRecord(
        eps=eps, codigo_cups=cups, valor_pactado=1000,
    ))
    db.commit()


class TestTarifaCoincidente:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/tarifa-coincidente")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_conceptos_ta"] == 0
        assert d["cobertura_pct"] == 0.0

    def test_con_tarifa_match(self, client, db_session):
        _seed_glosa(db_session, 1, "SANITAS")
        _seed_concepto(db_session, 1, cups="906625")
        _seed_tarifa(db_session, "SANITAS", "906625")

        r = client.get("/glosas/stats/tarifa-coincidente")
        d = r.json()
        assert d["con_tarifa_pactada"] == 1
        assert d["sin_tarifa_pactada"] == 0
        assert d["cobertura_pct"] == 100.0

    def test_sin_tarifa_match(self, client, db_session):
        _seed_glosa(db_session, 1, "SANITAS")
        _seed_concepto(db_session, 1, cups="999999")
        # No hay tarifa para SANITAS+999999

        r = client.get("/glosas/stats/tarifa-coincidente")
        d = r.json()
        assert d["sin_tarifa_pactada"] == 1
        assert d["cobertura_pct"] == 0.0

    def test_filtra_solo_TA(self, client, db_session):
        _seed_glosa(db_session, 1, "SANITAS")
        # Concepto FA → no debe entrar (no es TA)
        _seed_concepto(db_session, 1, codigo_glosa="FA0603",
                       cups="906625")
        r = client.get("/glosas/stats/tarifa-coincidente")
        d = r.json()
        assert d["total_conceptos_ta"] == 0

    def test_cobertura_50pct(self, client, db_session):
        _seed_glosa(db_session, 1, "SANITAS")
        _seed_concepto(db_session, 1, cups="111")
        _seed_concepto(db_session, 1, cups="222")
        # Solo 111 tiene tarifa
        _seed_tarifa(db_session, "SANITAS", "111")

        r = client.get("/glosas/stats/tarifa-coincidente")
        d = r.json()
        assert d["con_tarifa_pactada"] == 1
        assert d["sin_tarifa_pactada"] == 1
        assert d["cobertura_pct"] == 50.0
