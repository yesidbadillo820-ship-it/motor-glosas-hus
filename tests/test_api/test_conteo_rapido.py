"""Tests del endpoint GET /admin/conteo-rapido (R135 P2)."""
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
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestConteoRapido:
    def test_estructura(self, client):
        r = client.get("/admin/conteo-rapido")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("glosas_total", "glosas_abiertas", "glosas_cerradas",
                    "glosas_criticas", "glosas_vencidas",
                    "usuarios_activos", "audit_log_24h",
                    "consultado_en"):
            assert key in d
        assert d["usuarios_activos"] == 1  # el SUPER_ADMIN seed

    def test_conteos(self, client, db_session):
        _seed(db_session, dias_restantes=10)        # abierta en tiempo
        _seed(db_session, dias_restantes=2)         # crítica
        _seed(db_session, dias_restantes=-5)        # vencida
        _seed(db_session, estado="LEVANTADA")       # cerrada
        _seed(db_session, estado="ACEPTADA")        # cerrada

        r = client.get("/admin/conteo-rapido")
        d = r.json()
        assert d["glosas_total"] == 5
        assert d["glosas_cerradas"] == 2
        assert d["glosas_abiertas"] == 3
        assert d["glosas_criticas"] == 1
        assert d["glosas_vencidas"] == 1

    def test_solo_cuenta_usuarios_activos(self, client, db_session):
        # Agregar uno inactivo
        db_session.add(UsuarioRecord(
            id=2, email="off@x", rol="AUDITOR", activo=0,
            password_hash=get_password_hash("y"),
        ))
        db_session.commit()
        r = client.get("/admin/conteo-rapido")
        d = r.json()
        # Solo el root del seed, no el desactivado
        assert d["usuarios_activos"] == 1
