"""Tests del endpoint GET /admin/anomalias-asignacion (R390 P1)."""
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
def admin():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, eps="X", gestor=None, estado="RADICADA", valor=1000):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestAnomaliasAsignacion:
    def test_gestor_especializado(self, client, db_session):
        # Alice tiene 9 de 10 glosas de SAN abiertas
        for _ in range(9):
            _seed(db_session, "SAN", "Alice")
        _seed(db_session, "SAN", "Bob")
        r = client.get("/admin/anomalias-asignacion")
        d = r.json()
        items = [
            x for x in d["items"]
            if x["tipo"] == "GESTOR_ESPECIALIZADO"
            and x["gestor"] == "Alice"
        ]
        assert len(items) >= 1

    def test_valor_concentrado(self, client, db_session):
        # Alice tiene 90% del valor
        _seed(db_session, "X", "Alice", valor=9_000_000)
        _seed(db_session, "X", "Bob", valor=1_000_000)
        r = client.get("/admin/anomalias-asignacion")
        d = r.json()
        items = [
            x for x in d["items"]
            if x["tipo"] == "VALOR_CONCENTRADO"
            and x["gestor"] == "Alice"
        ]
        assert len(items) == 1
