"""Tests del endpoint GET /glosas/stats/conciliaciones-acta-firmadas (R366 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ConciliacionRecord,
    GlosaRecord,
    UsuarioRecord,
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


def _seed_glosa(db, glosa_id):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_concil(db, glosa_id, estado, acta=None):
    db.add(ConciliacionRecord(
        glosa_id=glosa_id, estado_bilateral=estado,
        valor_conciliado=1000,
        acta_numero=acta,
        fecha_acta=ahora_utc() if acta else None,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestConciliacionesActaFirmadas:
    def test_filtra(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_concil(db_session, 1, "ACTA_FIRMADA", acta="A001")
        _seed_concil(db_session, 1, "CERRADA", acta="A002")
        _seed_concil(db_session, 1, "PROGRAMADA")  # no firmada

        r = client.get(
            "/glosas/stats/conciliaciones-acta-firmadas"
        )
        d = r.json()
        assert d["total_actas"] == 2
        actas = {it["acta_numero"] for it in d["items"]}
        assert actas == {"A001", "A002"}
