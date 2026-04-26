"""Tests del endpoint GET /usuarios/yo/eps-asignadas (R310 P1)."""
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
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice", rol="AUDITOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gestor, eps, estado="RADICADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestYoEPSAsignadas:
    def test_lista(self, client, db_session):
        _seed(db_session, "Alice", "SANITAS", estado="LEVANTADA")
        _seed(db_session, "Alice", "SANITAS", estado="RADICADA")
        _seed(db_session, "Alice", "EPS001")
        _seed(db_session, "Bob", "OTRA")  # no propia

        r = client.get("/usuarios/yo/eps-asignadas")
        d = r.json()
        assert d["total_eps"] == 2
        sanitas = next(x for x in d["items"] if x["eps"] == "SANITAS")
        assert sanitas["count_total"] == 2
        assert sanitas["count_abiertas"] == 1
        assert sanitas["tasa_levantamiento_pct"] == 100.0
