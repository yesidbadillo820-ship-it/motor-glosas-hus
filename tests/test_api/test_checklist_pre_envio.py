"""Tests del endpoint GET /glosas/{id}/checklist-pre-envio (R215 P1)."""
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


def _seed(db, **kw):
    base = dict(
        id=1, eps="SANITAS", paciente="X", codigo_glosa="TA0201",
        factura="F-1", valor_objetado=1000,
        etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        dictamen="x" * 300,
        codigo_respuesta="RE9901",
        gestor_nombre="Alice",
        dias_restantes=10,
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestChecklistPreEnvio:
    def test_404(self, client):
        r = client.get("/glosas/99999/checklist-pre-envio")
        assert r.status_code == 404

    def test_estructura(self, client, db_session):
        _seed(db_session)
        r = client.get("/glosas/1/checklist-pre-envio")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("glosa_id", "checklist", "todos_ok", "faltantes"):
            assert key in d
        assert len(d["checklist"]) == 7  # 7 items

    def test_glosa_completa(self, client, db_session):
        _seed(db_session)
        r = client.get("/glosas/1/checklist-pre-envio")
        d = r.json()
        assert d["todos_ok"] is True
        assert d["faltantes"] == []

    def test_glosa_con_faltantes(self, client, db_session):
        _seed(db_session,
              dictamen="corto",  # < 200 chars
              gestor_nombre=None)
        r = client.get("/glosas/1/checklist-pre-envio")
        d = r.json()
        assert d["todos_ok"] is False
        assert "Gestor asignado" in d["faltantes"]
        assert any("Dictamen" in f for f in d["faltantes"])

    def test_vencida_falla(self, client, db_session):
        _seed(db_session, dias_restantes=-5)
        r = client.get("/glosas/1/checklist-pre-envio")
        d = r.json()
        assert d["todos_ok"] is False
        assert "No vencida" in d["faltantes"]
