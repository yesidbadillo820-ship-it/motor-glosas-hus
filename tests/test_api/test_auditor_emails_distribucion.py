"""Tests del endpoint GET /glosas/stats/auditor-emails-distribucion (R327 P1)."""
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
def coord():
    return UsuarioRecord(
        id=1, email="coord@hus.com", rol="COORDINADOR", activo=1,
    )


@pytest.fixture
def client(db_session, coord):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, email, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        auditor_email=email,
    ))
    db.commit()


class TestAuditorEmailsDistribucion:
    def test_distribucion(self, client, db_session):
        _seed(db_session, "alice@x", estado="RADICADA")
        _seed(db_session, "alice@x", estado="LEVANTADA")
        _seed(db_session, "bob@x", estado="RATIFICADA")

        r = client.get(
            "/glosas/stats/auditor-emails-distribucion"
        )
        d = r.json()
        b = {it["auditor_email"]: it for it in d["items"]}
        assert b["alice@x"]["total"] == 2
        assert b["alice@x"]["abiertas"] == 1
        assert b["alice@x"]["decididas"] == 1
        assert b["bob@x"]["decididas"] == 1
