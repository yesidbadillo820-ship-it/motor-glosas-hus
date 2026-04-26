"""Tests del endpoint GET /glosas/stats/tercero-nit-resumen (R265 P1)."""
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


def _seed(db, nit, eps="X", valor=1000, recuperado=0, nombre=None):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, valor_recuperado=recuperado,
        etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        tercero_nit=nit,
        tercero_nombre=nombre,
    ))
    db.commit()


class TestTerceroNitResumen:
    def test_agrupa_por_nit(self, client, db_session):
        _seed(db_session, "900111", eps="SANITAS", nombre="SANITAS S.A.")
        _seed(db_session, "900111", eps="SANITAS COMPL", nombre="SANITAS S.A.")
        _seed(db_session, "900222", eps="EPS001", nombre="EPS001 S.A.")

        r = client.get("/glosas/stats/tercero-nit-resumen")
        d = r.json()
        assert d["total_terceros"] == 2
        sanitas = next(x for x in d["items"] if x["tercero_nit"] == "900111")
        assert sanitas["count_glosas"] == 2
        assert sanitas["eps_distintas"] == 2

    def test_excluye_sin_nit(self, client, db_session):
        _seed(db_session, None)
        _seed(db_session, "")
        _seed(db_session, "900333")
        r = client.get("/glosas/stats/tercero-nit-resumen")
        d = r.json()
        assert d["total_terceros"] == 1

    def test_orden_por_valor(self, client, db_session):
        _seed(db_session, "A", valor=100)
        _seed(db_session, "B", valor=999)
        _seed(db_session, "C", valor=500)
        r = client.get("/glosas/stats/tercero-nit-resumen")
        d = r.json()
        valores = [it["valor_objetado_total"] for it in d["items"]]
        assert valores == sorted(valores, reverse=True)
