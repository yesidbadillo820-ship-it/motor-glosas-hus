"""Tests del endpoint GET /admin/glosas-vencen-manana (R358 P1)."""
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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, dias_restantes, estado="RADICADA", valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dias_restantes=dias_restantes,
    ))
    db.commit()


class TestGlosasVencenManana:
    def test_filtra(self, client, db_session):
        _seed(db_session, dias_restantes=1, valor=1000)
        _seed(db_session, dias_restantes=1, valor=2000)
        _seed(db_session, dias_restantes=2)  # no
        _seed(db_session, dias_restantes=0)  # no

        r = client.get("/admin/glosas-vencen-manana")
        d = r.json()
        assert d["total_vencen_manana"] == 2
        assert d["valor_total"] == 3000

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, dias_restantes=1, estado="LEVANTADA")
        r = client.get("/admin/glosas-vencen-manana")
        d = r.json()
        assert d["total_vencen_manana"] == 0
