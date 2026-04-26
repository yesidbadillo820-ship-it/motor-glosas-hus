"""Tests del endpoint GET /glosas/stats/concentracion-codigo (R146 P1)."""
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


def _seed(db, codigo, valor=1000, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa=codigo,
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestConcentracionCodigo:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/concentracion-codigo")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []
        assert d["valor_pendiente_total"] == 0

    def test_orden_por_valor_desc(self, client, db_session):
        # TA0201: $30k pendiente
        _seed(db_session, "TA0201", valor=10_000)
        _seed(db_session, "TA0201", valor=20_000)
        # FA0603: $5k
        _seed(db_session, "FA0603", valor=5_000)

        r = client.get("/glosas/stats/concentracion-codigo")
        d = r.json()
        assert d["items"][0]["codigo_glosa"] == "TA0201"
        assert d["items"][0]["valor_pendiente"] == 30_000
        assert d["items"][1]["codigo_glosa"] == "FA0603"

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, "X", valor=99_999, estado="LEVANTADA")
        r = client.get("/glosas/stats/concentracion-codigo")
        d = r.json()
        assert d["items"] == []

    def test_pct_consistente(self, client, db_session):
        _seed(db_session, "A", valor=80)
        _seed(db_session, "B", valor=20)
        r = client.get("/glosas/stats/concentracion-codigo")
        d = r.json()
        items = {it["codigo_glosa"]: it for it in d["items"]}
        assert items["A"]["pct_del_total"] == 80.0
        assert items["B"]["pct_del_total"] == 20.0

    def test_codigo_null_se_clasifica_como_sin_codigo(self, client, db_session):
        # Glosa sin codigo_glosa
        db_session.add(GlosaRecord(
            eps="X", paciente="X", codigo_glosa=None,
            valor_objetado=500, etapa="X", estado="RADICADA",
            creado_en=ahora_utc(),
        ))
        db_session.commit()

        r = client.get("/glosas/stats/concentracion-codigo")
        d = r.json()
        codigos = {it["codigo_glosa"] for it in d["items"]}
        assert "(SIN_CODIGO)" in codigos
