"""Tests del endpoint GET /admin/glosas-prioritarias (R112 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
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
def usuario_super(db_session):
    u = UsuarioRecord(
        id=1, email="root@hus.gov.co", rol="SUPER_ADMIN", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_super):
    from app.api.deps import get_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_admin] = lambda: usuario_super
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=100, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        dictamen="<p>" + "x" * 100 + "</p>",
        gestor_nombre="Alice",
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestGlosasPrioritarias:
    def test_vacio(self, client):
        r = client.get("/admin/glosas-prioritarias")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, dias_restantes=-100, estado="ACEPTADA")
        _seed(db_session, dias_restantes=-100, estado="LEVANTADA")
        r = client.get("/admin/glosas-prioritarias")
        d = r.json()
        assert d["items"] == []

    def test_vencida_score_alto(self, client, db_session):
        _seed(db_session, dias_restantes=-10)
        r = client.get("/admin/glosas-prioritarias")
        d = r.json()
        assert len(d["items"]) == 1
        # vencida = +100
        assert d["items"][0]["score"] >= 100
        assert any("vencida" in r for r in d["items"][0]["razones"])

    def test_alto_valor_score(self, client, db_session):
        _seed(db_session, dias_restantes=30, valor_objetado=20_000_000)
        r = client.get("/admin/glosas-prioritarias")
        d = r.json()
        assert len(d["items"]) == 1
        assert any("alto valor" in r for r in d["items"][0]["razones"])

    def test_orden_por_score_desc(self, client, db_session):
        # Glosa 1: vencida (+100) + alto valor (+30) = 130
        _seed(db_session, dias_restantes=-5, valor_objetado=20_000_000)
        # Glosa 2: solo crítica (+50)
        _seed(db_session, dias_restantes=2)
        # Glosa 3: sin dictamen (+25)
        _seed(db_session, dictamen=None, dias_restantes=20)
        r = client.get("/admin/glosas-prioritarias")
        d = r.json()
        scores = [it["score"] for it in d["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_glosa_sin_issues_no_aparece(self, client, db_session):
        # Glosa con todo OK, no debe entrar al ranking
        _seed(db_session, dias_restantes=30, valor_objetado=100,
              dictamen="x" * 100, gestor_nombre="Alice")
        r = client.get("/admin/glosas-prioritarias")
        d = r.json()
        assert d["items"] == []
