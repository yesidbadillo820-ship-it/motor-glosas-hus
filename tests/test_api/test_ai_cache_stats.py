"""Tests del endpoint /admin/ai-cache/stats (R86 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AICacheRecord, UsuarioRecord


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
        clave="x" * 64, modelo="x", respuesta="r" * 100,
        hit_count=0, creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(AICacheRecord(**base))
    db.commit()


class TestAiCacheStats:
    def test_vacio(self, client):
        r = client.get("/admin/ai-cache/stats")
        assert r.status_code == 200
        d = r.json()
        assert d["total_entradas"] == 0
        assert d["top_5_mas_usadas"] == []

    def test_estadisticas_basicas(self, client, db_session):
        _seed(db_session, clave="a" * 64, hit_count=5, respuesta="r" * 200)
        _seed(db_session, clave="b" * 64, hit_count=10, respuesta="r" * 300)
        _seed(db_session, clave="c" * 64, hit_count=2, respuesta="r" * 100)
        r = client.get("/admin/ai-cache/stats")
        d = r.json()
        assert d["total_entradas"] == 3
        assert d["hit_count_total"] == 17  # 5+10+2
        assert d["hit_count_max"] == 10
        # Espacio: 200+300+100 = 600 chars
        assert d["espacio_chars"] == 600

    def test_top_5_ordenado_por_hits(self, client, db_session):
        for hits in [1, 5, 100, 50, 10, 200, 3]:
            _seed(db_session,
                  clave=("0" * 60 + str(hits))[:64],
                  hit_count=hits)
        r = client.get("/admin/ai-cache/stats")
        d = r.json()
        # Top 5 ordenado DESC: 200, 100, 50, 10, 5
        hits_top = [it["hits"] for it in d["top_5_mas_usadas"]]
        assert hits_top == [200, 100, 50, 10, 5]

    def test_viejas_30d(self, client, db_session):
        _seed(db_session, clave="a" * 64,
              creado_en=ahora_utc() - timedelta(days=60))
        _seed(db_session, clave="b" * 64, creado_en=ahora_utc())
        r = client.get("/admin/ai-cache/stats")
        d = r.json()
        assert d["viejas_30d"] == 1
