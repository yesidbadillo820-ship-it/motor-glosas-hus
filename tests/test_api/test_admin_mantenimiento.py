"""Tests del endpoint POST /admin/mantenimiento/purgar (R83 P1)."""
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
from app.models.db import (
    AICacheRecord, AICallRecord, GlosaEliminadaRecord, UsuarioRecord,
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


class TestMantenimientoPurgar:
    def test_dry_run_devuelve_stats_sin_borrar(self, client, db_session):
        # Seed cosas viejas
        db_session.add(AICacheRecord(
            clave="x" * 64, modelo="x", respuesta="r",
            creado_en=ahora_utc() - timedelta(days=60),
        ))
        db_session.commit()
        r = client.post("/admin/mantenimiento/purgar?dry_run=true")
        assert r.status_code == 200, r.text
        d = r.json()
        # Estructura
        assert "ai_cache" in d
        assert "ai_calls" in d
        assert "papelera" in d
        # dry_run = true → obsoletas se cuentan pero no se borran
        assert d["ai_cache"]["obsoletas"] == 1
        assert d["ai_cache"]["purgadas"] == 0
        assert db_session.query(AICacheRecord).count() == 1  # sigue ahí

    def test_real_purga_obsoletas(self, client, db_session):
        db_session.add(AICacheRecord(
            clave="a" * 64, modelo="x", respuesta="vieja",
            creado_en=ahora_utc() - timedelta(days=60),
        ))
        db_session.add(AICacheRecord(
            clave="b" * 64, modelo="x", respuesta="reciente",
            creado_en=ahora_utc(),
        ))
        db_session.commit()
        r = client.post("/admin/mantenimiento/purgar")
        d = r.json()
        assert d["ai_cache"]["purgadas"] == 1
        # Solo queda la reciente
        assert db_session.query(AICacheRecord).count() == 1

    def test_estructura_completa(self, client):
        r = client.post("/admin/mantenimiento/purgar?dry_run=true")
        d = r.json()
        for tabla in ("ai_cache", "ai_calls", "papelera"):
            for k in ("total_antes", "obsoletas", "purgadas",
                      "dias_corte", "dry_run"):
                assert k in d[tabla], f"falta {k} en {tabla}"

    def test_purga_calls_viejos_90d(self, client, db_session):
        db_session.add(AICallRecord(
            proveedor="anthropic", modelo="x", cost_usd=0.01,
            creado_en=ahora_utc() - timedelta(days=120),
        ))
        db_session.commit()
        r = client.post("/admin/mantenimiento/purgar")
        d = r.json()
        assert d["ai_calls"]["purgadas"] == 1

    def test_purga_papelera_caducada(self, client, db_session):
        import json
        db_session.add(GlosaEliminadaRecord(
            glosa_id_original=1,
            snapshot_json=json.dumps({}),
            eliminado_por="x@hus.com",
            eliminado_en=ahora_utc() - timedelta(days=40),
        ))
        db_session.commit()
        r = client.post("/admin/mantenimiento/purgar")
        d = r.json()
        assert d["papelera"]["purgadas"] == 1
