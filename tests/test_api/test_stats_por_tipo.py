"""Tests del endpoint /glosas/stats/por-tipo (R68 P3)."""
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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100_000, valor_aceptado=0,
        etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestStatsPorTipo:
    def test_sin_glosas(self, client):
        r = client.get("/glosas/stats/por-tipo")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 0

    def test_agrupacion_por_prefijo(self, client, db_session):
        # 3 TA, 2 SO, 1 AU
        _seed(db_session, codigo_glosa="TA0201")
        _seed(db_session, codigo_glosa="TA0202")
        _seed(db_session, codigo_glosa="TA0801")
        _seed(db_session, codigo_glosa="SO0101")
        _seed(db_session, codigo_glosa="SO0202")
        _seed(db_session, codigo_glosa="AU0101")
        r = client.get("/glosas/stats/por-tipo")
        d = r.json()
        # Top: TA con 3
        ta = next(x for x in d["items"] if x["prefijo"] == "TA")
        so = next(x for x in d["items"] if x["prefijo"] == "SO")
        au = next(x for x in d["items"] if x["prefijo"] == "AU")
        assert ta["count"] == 3
        assert so["count"] == 2
        assert au["count"] == 1

    def test_codigos_distintos_se_cuentan(self, client, db_session):
        """codigos_distintos debe ser 2 cuando hay TA0201 y TA0202."""
        _seed(db_session, codigo_glosa="TA0201")
        _seed(db_session, codigo_glosa="TA0201")  # mismo
        _seed(db_session, codigo_glosa="TA0202")
        r = client.get("/glosas/stats/por-tipo")
        ta = next(x for x in r.json()["items"] if x["prefijo"] == "TA")
        assert ta["codigos_distintos"] == 2
        assert ta["count"] == 3

    def test_descripciones_humanas(self, client, db_session):
        _seed(db_session, codigo_glosa="TA0201")
        _seed(db_session, codigo_glosa="SO0101")
        r = client.get("/glosas/stats/por-tipo")
        d = r.json()
        for it in d["items"]:
            if it["prefijo"] == "TA":
                assert "Tarifa" in it["tipo"]
            if it["prefijo"] == "SO":
                assert "Soportes" in it["tipo"]

    def test_orden_por_count_desc(self, client, db_session):
        for _ in range(5):
            _seed(db_session, codigo_glosa="SO0101")
        for _ in range(2):
            _seed(db_session, codigo_glosa="TA0201")
        r = client.get("/glosas/stats/por-tipo")
        items = r.json()["items"]
        assert items[0]["prefijo"] == "SO"
        assert items[1]["prefijo"] == "TA"

    def test_porcentajes_suman_100(self, client, db_session):
        _seed(db_session, codigo_glosa="TA0201")
        _seed(db_session, codigo_glosa="SO0101")
        _seed(db_session, codigo_glosa="AU0101")
        r = client.get("/glosas/stats/por-tipo")
        suma = sum(x["porcentaje"] for x in r.json()["items"])
        assert abs(suma - 100.0) < 0.5
