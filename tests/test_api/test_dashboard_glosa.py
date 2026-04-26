"""Tests del endpoint GET /glosas/{id}/dashboard (R217 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ComentarioGlosaRecord, ConceptoGlosaRecord,
    DictamenVersionRecord, GlosaRecord, UsuarioRecord,
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


def _seed_glosa(db, gid):
    db.add(GlosaRecord(
        id=gid, eps="SANITAS", paciente="X", codigo_glosa="C",
        factura="F-1", valor_objetado=10000,
        etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        dias_restantes=5,
    ))
    db.commit()


class TestDashboardGlosa:
    def test_404(self, client):
        r = client.get("/glosas/99999/dashboard")
        assert r.status_code == 404

    def test_estructura(self, client, db_session):
        _seed_glosa(db_session, 1)
        r = client.get("/glosas/1/dashboard")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("glosa_id", "datos", "contadores"):
            assert key in d
        for k in ("eps", "factura", "estado", "valor_objetado",
                  "valor_recuperado", "dias_restantes"):
            assert k in d["datos"]
        for k in ("conceptos", "versiones_dictamen", "comentarios",
                  "menciones_pendientes", "conciliaciones",
                  "eventos_audit"):
            assert k in d["contadores"]

    def test_contadores_correctos(self, client, db_session):
        _seed_glosa(db_session, 1)
        # 2 conceptos
        for _ in range(2):
            db_session.add(ConceptoGlosaRecord(
                glosa_id=1, codigo_glosa="C", valor_objetado=100,
            ))
        # 3 versiones
        for _ in range(3):
            db_session.add(DictamenVersionRecord(
                glosa_id=1, dictamen_html="x", accion="REFINAR",
                creado_en=ahora_utc(),
            ))
        # 1 comentario con mención no resuelta
        db_session.add(ComentarioGlosaRecord(
            glosa_id=1, autor_email="u@x", texto="x",
            mencion="resp@x", resuelto=0,
            creado_en=ahora_utc(),
        ))
        db_session.commit()

        r = client.get("/glosas/1/dashboard")
        d = r.json()
        assert d["contadores"]["conceptos"] == 2
        assert d["contadores"]["versiones_dictamen"] == 3
        assert d["contadores"]["comentarios"] == 1
        assert d["contadores"]["menciones_pendientes"] == 1
