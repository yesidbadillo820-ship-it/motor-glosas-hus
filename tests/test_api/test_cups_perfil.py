"""Tests del endpoint GET /glosas/cups-perfil (R140 P2)."""
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


def _seed_glosa(db, gid, eps="X"):
    db.add(GlosaRecord(
        id=gid, eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_concepto(db, gid, cups, **kw):
    base = dict(
        glosa_id=gid, codigo_glosa="TA0201",
        cups_codigo=cups, valor_objetado=1000,
    )
    base.update(kw)
    db.add(ConceptoGlosaRecord(**base))
    db.commit()


class TestCupsPerfil:
    def test_sin_historial(self, client):
        r = client.get("/glosas/cups-perfil?cups=999999")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["sin_historial"] is True

    def test_estructura_completa(self, client, db_session):
        _seed_glosa(db_session, 1, eps="SANITAS")
        _seed_glosa(db_session, 2, eps="NUEVA EPS")
        _seed_concepto(db_session, 1, "906625",
                       cups_descripcion="Gonadotropina",
                       centro_costo="LAB", valor_objetado=10_000)
        _seed_concepto(db_session, 2, "906625",
                       centro_costo="LAB", valor_objetado=20_000)

        r = client.get("/glosas/cups-perfil?cups=906625")
        d = r.json()
        assert d["sin_historial"] is False
        assert d["frecuencia_total"] == 2
        assert d["valor_objetado_total"] == 30_000
        assert d["valor_promedio"] == 15000.0
        assert "Gonadotropina" in d["cups_descripcion"]
        # Por EPS
        assert d["por_eps"] == {"SANITAS": 1, "NUEVA EPS": 1}
        assert d["centros_costo"] == ["LAB"]

    def test_aislamiento_por_cups(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_concepto(db_session, 1, "AAA", valor_objetado=999)
        _seed_concepto(db_session, 1, "BBB", valor_objetado=1)

        r = client.get("/glosas/cups-perfil?cups=AAA")
        d = r.json()
        assert d["frecuencia_total"] == 1
        assert d["valor_objetado_total"] == 999
