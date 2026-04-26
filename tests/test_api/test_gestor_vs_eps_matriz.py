"""Tests del endpoint GET /glosas/stats/gestor-vs-eps-matriz (R296 P1)."""
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


def _seed(db, gestor, eps):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="LEVANTADA",
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestGestorVsEPSMatriz:
    def test_matriz(self, client, db_session):
        _seed(db_session, "Alice", "SANITAS")
        _seed(db_session, "Alice", "SANITAS")
        _seed(db_session, "Alice", "EPS001")
        _seed(db_session, "Bob", "SANITAS")

        r = client.get("/glosas/stats/gestor-vs-eps-matriz")
        d = r.json()
        assert "Alice" in d["gestores"]
        assert "Bob" in d["gestores"]
        assert "SANITAS" in d["eps"]
        assert d["matriz"]["Alice"]["SANITAS"] == 2
        assert d["matriz"]["Alice"]["EPS001"] == 1
        assert d["matriz"]["Bob"]["SANITAS"] == 1

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
            r = c.get("/glosas/stats/gestor-vs-eps-matriz")
            assert r.status_code == 403
        app.dependency_overrides.clear()
