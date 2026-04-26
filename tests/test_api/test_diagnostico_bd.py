"""Tests del endpoint GET /admin/diagnostico-bd (R101 P2)."""
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


class TestDiagnosticoBD:
    def test_estructura(self, client):
        r = client.get("/admin/diagnostico-bd")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_filas_todas_tablas", "total_estimado_mb", "items"):
            assert key in d
        assert isinstance(d["items"], list)

    def test_lista_tablas_principales(self, client):
        r = client.get("/admin/diagnostico-bd")
        d = r.json()
        nombres = {it["tabla"] for it in d["items"]}
        assert "glosas" in nombres
        assert "usuarios" in nombres
        assert "audit_log" in nombres
        assert "ai_cache" in nombres

    def test_conteo_correcto_glosas(self, client, db_session):
        for _ in range(5):
            db_session.add(GlosaRecord(
                eps="X", paciente="X", codigo_glosa="C",
                valor_objetado=100, etapa="X", estado="RADICADA",
                creado_en=ahora_utc(),
            ))
        db_session.commit()

        r = client.get("/admin/diagnostico-bd")
        d = r.json()
        glosas = next(it for it in d["items"] if it["tabla"] == "glosas")
        assert glosas["filas"] == 5
        assert glosas["tamano_estimado_mb"] > 0

    def test_orden_por_tamano_desc(self, client):
        r = client.get("/admin/diagnostico-bd")
        d = r.json()
        tamanos = [it["tamano_estimado_mb"] for it in d["items"]]
        assert tamanos == sorted(tamanos, reverse=True)
