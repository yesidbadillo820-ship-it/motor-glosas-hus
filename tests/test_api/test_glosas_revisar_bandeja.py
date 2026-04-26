"""Tests del endpoint GET /admin/glosas-revisar-bandeja (R256 P1)."""
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


class TestGlosasRevisarBandeja:
    def test_estructura(self, client):
        r = client.get("/admin/glosas-revisar-bandeja")
        d = r.json()
        for key in ("total_pendiente_eps", "total_listas_envio",
                    "pendiente_eps", "listas_envio"):
            assert key in d

    def test_pendiente_eps(self, client, db_session):
        # RESPONDIDA hace 10 días sin decision → pendiente
        _seed(db_session, estado="RESPONDIDA",
              creado_en=ahora_utc() - timedelta(days=10))
        # RESPONDIDA hace 3 días → no
        _seed(db_session, estado="RESPONDIDA",
              creado_en=ahora_utc() - timedelta(days=3))

        r = client.get("/admin/glosas-revisar-bandeja")
        d = r.json()
        assert d["total_pendiente_eps"] == 1

    def test_listas_envio(self, client, db_session):
        _seed(db_session, estado="RADICADA", dictamen="x" * 300)
        # Dictamen corto → no aplica
        _seed(db_session, estado="RADICADA", dictamen="corto")

        r = client.get("/admin/glosas-revisar-bandeja")
        d = r.json()
        assert d["total_listas_envio"] == 1
