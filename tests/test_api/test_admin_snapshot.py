"""Tests del endpoint GET /admin/snapshot.json (R117 P1)."""
from __future__ import annotations

import json

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
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestAdminSnapshot:
    def test_content_type_y_attachment(self, client):
        r = client.get("/admin/snapshot.json")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/json"
        assert "attachment" in r.headers["content-disposition"]
        assert ".json" in r.headers["content-disposition"]

    def test_estructura(self, client):
        r = client.get("/admin/snapshot.json")
        d = json.loads(r.content)
        for key in ("snapshot_id", "generado_en", "generado_por",
                    "counts", "glosas"):
            assert key in d

    def test_counts_correctos(self, client, db_session):
        for _ in range(3):
            _seed(db_session)
        r = client.get("/admin/snapshot.json")
        d = json.loads(r.content)
        assert d["counts"]["glosas_total"] == 3
        assert d["counts"]["usuarios_activos"] == 1  # el SUPER_ADMIN seed

    def test_glosas_abiertas_vs_cerradas(self, client, db_session):
        _seed(db_session, estado="RADICADA", valor_objetado=10_000)
        _seed(db_session, estado="LEVANTADA", valor_recuperado=5_000)
        r = client.get("/admin/snapshot.json")
        d = json.loads(r.content)
        assert d["glosas"]["abiertas"] == 1
        assert d["glosas"]["cerradas"] == 1
        assert d["glosas"]["valor_pendiente_total"] == 10_000
        assert d["glosas"]["valor_recuperado_acumulado"] == 5_000

    def test_snapshot_id_formato(self, client):
        r = client.get("/admin/snapshot.json")
        d = json.loads(r.content)
        # YYYYMMDD-HHMMSS
        assert "-" in d["snapshot_id"]
        assert len(d["snapshot_id"]) == 15
