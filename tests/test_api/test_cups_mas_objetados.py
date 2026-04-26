"""Tests del endpoint GET /glosas/stats/cups-mas-objetados (R140 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ConceptoGlosaRecord, GlosaRecord, UsuarioRecord,
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


def _seed_concepto(db, cups, valor=1000, factura="F-1", descripcion=None):
    db.add(ConceptoGlosaRecord(
        glosa_id=1, codigo_glosa="C", factura=factura,
        cups_codigo=cups, cups_descripcion=descripcion,
        valor_objetado=valor,
    ))
    db.commit()


class TestCupsMasObjetados:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/cups-mas-objetados")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []
        assert d["total_cups_unicos"] == 0

    def test_orden_por_frecuencia_desc(self, client, db_session):
        for _ in range(5):
            _seed_concepto(db_session, "906625", descripcion="Gonadotropina")
        for _ in range(2):
            _seed_concepto(db_session, "FMQ0163",
                           descripcion="Procedimiento Q")
        _seed_concepto(db_session, "39143A", descripcion="Otro")

        r = client.get("/glosas/stats/cups-mas-objetados")
        d = r.json()
        cups = [it["cups_codigo"] for it in d["items"]]
        assert cups == ["906625", "FMQ0163", "39143A"]
        assert d["items"][0]["frecuencia"] == 5

    def test_acumula_valor(self, client, db_session):
        _seed_concepto(db_session, "X", valor=1000)
        _seed_concepto(db_session, "X", valor=2500)
        r = client.get("/glosas/stats/cups-mas-objetados")
        d = r.json()
        assert d["items"][0]["valor_objetado_total"] == 3500

    def test_facturas_distintas(self, client, db_session):
        _seed_concepto(db_session, "X", factura="F-1")
        _seed_concepto(db_session, "X", factura="F-1")  # dup
        _seed_concepto(db_session, "X", factura="F-2")
        r = client.get("/glosas/stats/cups-mas-objetados")
        d = r.json()
        assert d["items"][0]["facturas_distintas"] == 2

    def test_excluye_cups_null(self, client, db_session):
        # Concepto sin CUPS no aparece
        db_session.add(ConceptoGlosaRecord(
            glosa_id=1, codigo_glosa="C", factura="F-1",
            cups_codigo=None, valor_objetado=99999,
        ))
        db_session.commit()
        r = client.get("/glosas/stats/cups-mas-objetados")
        d = r.json()
        assert d["items"] == []

    def test_top_limita(self, client, db_session):
        for i in range(10):
            _seed_concepto(db_session, f"CUPS{i}")
        r = client.get("/glosas/stats/cups-mas-objetados?top=3")
        d = r.json()
        assert len(d["items"]) == 3
