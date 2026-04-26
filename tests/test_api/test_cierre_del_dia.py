"""Tests del endpoint GET /admin/cierre-del-dia (R122 P1)."""
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
from app.models.db import AuditLogRecord, GlosaRecord, UsuarioRecord


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


def _seed_glosa(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


def _seed_audit(db, usuario, horas_atras=1):
    db.add(AuditLogRecord(
        usuario_email=usuario, accion="X", tabla="glosas",
        timestamp=ahora_utc() - timedelta(hours=horas_atras),
    ))
    db.commit()


class TestCierreDelDia:
    def test_estructura(self, client):
        r = client.get("/admin/cierre-del-dia")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("fecha_reporte", "ventana_horas", "glosas_creadas_24h",
                    "glosas_cerradas_24h", "valor_recuperado_24h",
                    "ia_calls_24h", "top_3_gestores", "vencen_manana"):
            assert key in d
        assert d["ventana_horas"] == 24

    def test_glosas_creadas_24h(self, client, db_session):
        # Reciente (10h atrás) → cuenta
        _seed_glosa(db_session, creado_en=ahora_utc() - timedelta(hours=10))
        # Vieja (30h atrás) → no cuenta
        _seed_glosa(db_session, creado_en=ahora_utc() - timedelta(hours=30))
        r = client.get("/admin/cierre-del-dia")
        d = r.json()
        assert d["glosas_creadas_24h"] == 1

    def test_cerradas_y_valor(self, client, db_session):
        # Cerrada en últimas 24h con $5k recuperado
        _seed_glosa(db_session,
                    estado="LEVANTADA",
                    valor_recuperado=5000,
                    fecha_decision_eps=ahora_utc() - timedelta(hours=2))
        # Cerrada hace 48h (fuera de ventana)
        _seed_glosa(db_session,
                    estado="LEVANTADA",
                    valor_recuperado=99999,
                    fecha_decision_eps=ahora_utc() - timedelta(hours=48))
        r = client.get("/admin/cierre-del-dia")
        d = r.json()
        assert d["glosas_cerradas_24h"] == 1
        assert d["valor_recuperado_24h"] == 5000

    def test_top_3_gestores(self, client, db_session):
        for _ in range(5):
            _seed_audit(db_session, "alice@x")
        for _ in range(3):
            _seed_audit(db_session, "bob@x")
        _seed_audit(db_session, "carol@x")

        r = client.get("/admin/cierre-del-dia")
        d = r.json()
        top = d["top_3_gestores"]
        assert len(top) == 3
        assert top[0] == {"usuario": "alice@x", "eventos": 5}
        assert top[1] == {"usuario": "bob@x", "eventos": 3}

    def test_vencen_manana(self, client, db_session):
        _seed_glosa(db_session, dias_restantes=1)
        _seed_glosa(db_session, dias_restantes=1, valor_objetado=5000)
        # No cuenta:
        _seed_glosa(db_session, dias_restantes=2)
        _seed_glosa(db_session, dias_restantes=1, estado="LEVANTADA")  # cerrada
        r = client.get("/admin/cierre-del-dia")
        d = r.json()
        assert d["vencen_manana"]["count"] == 2
        assert d["vencen_manana"]["valor_total"] == 6000
