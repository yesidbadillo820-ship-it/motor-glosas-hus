"""Tests del endpoint GET /glosas/stats/gestor-vencidas-distribucion (R323 P1)."""
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


def _seed(db, gestor, dias_restantes):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias_restantes,
    ))
    db.commit()


class TestGestorVencidasDistribucion:
    def test_distribucion(self, client, db_session):
        # Alice: 1 vencida, 1 crítica, 1 ok
        _seed(db_session, "Alice", -3)
        _seed(db_session, "Alice", 2)
        _seed(db_session, "Alice", 10)
        # Bob: 0 vencidas
        _seed(db_session, "Bob", 5)

        r = client.get(
            "/glosas/stats/gestor-vencidas-distribucion"
        )
        d = r.json()
        alice = next(x for x in d["items"] if x["gestor"] == "Alice")
        assert alice["total_abiertas"] == 3
        assert alice["vencidas"] == 1
        assert alice["criticas"] == 1
        assert alice["pct_vencidas"] == round(100 / 3, 2)

    def test_no_auditor(self, db_session):
        from app.api.deps import get_usuario_actual
        from app.main import app
        auditor = UsuarioRecord(
            id=99, email="x@x.com", rol="AUDITOR", activo=1,
        )
        app.dependency_overrides[get_db] = (
            lambda: iter([db_session]).__next__()
        )
        app.dependency_overrides[get_usuario_actual] = lambda: auditor
        with TestClient(app) as c:
            r = c.get(
                "/glosas/stats/gestor-vencidas-distribucion"
            )
            assert r.status_code == 403
        app.dependency_overrides.clear()
