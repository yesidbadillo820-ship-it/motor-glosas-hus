"""Tests del endpoint /admin/system-info (R73 P2)."""
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


class TestSystemInfo:
    def test_estructura_basica(self, client):
        r = client.get("/admin/system-info")
        assert r.status_code == 200
        d = r.json()
        for campo in ("counts", "schedulers", "env_configurada",
                      "consultado_por", "consultado_en"):
            assert campo in d

    def test_counts_completos(self, client):
        r = client.get("/admin/system-info")
        d = r.json()
        for k in ("glosas", "usuarios", "contratos", "tarifas_contratadas",
                  "plantillas_gold_activas", "ai_cache",
                  "ai_calls_30d", "audit_log_30d", "papelera"):
            assert k in d["counts"]

    def test_counts_numericos(self, client, db_session):
        # Seed 3 glosas
        for i in range(3):
            db_session.add(GlosaRecord(
                eps="X", paciente=f"P{i}", codigo_glosa="TA0201",
                valor_objetado=100, etapa="X", estado="RADICADA",
                creado_en=ahora_utc(),
            ))
        db_session.commit()
        r = client.get("/admin/system-info")
        d = r.json()
        assert d["counts"]["glosas"] == 3

    def test_env_no_revela_valores(self, client, monkeypatch):
        """SECURITY: env_configurada solo debe exponer bool, no valor."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-xxxxxx")
        r = client.get("/admin/system-info")
        d = r.json()
        # Solo bool, NO el valor
        assert d["env_configurada"]["ANTHROPIC_API_KEY"] is True
        # El valor NO debe estar en ningún lado
        assert "sk-secret-xxxxxx" not in r.text

    def test_consultado_por_es_email(self, client):
        r = client.get("/admin/system-info")
        d = r.json()
        assert d["consultado_por"] == "root@hus.gov.co"
