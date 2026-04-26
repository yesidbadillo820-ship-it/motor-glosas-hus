"""Tests del endpoint GET /admin/glosas-altas-cuantia-vencidas (R367 P1)."""
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


def _seed(db, valor, dias, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dias_restantes=dias,
    ))
    db.commit()


class TestGlosasAltasCuantiaVencidas:
    def test_filtra(self, client, db_session):
        # Red flag: alto valor Y vencida
        _seed(db_session, valor=10_000_000, dias=-5)
        # Bajo valor, no cuenta
        _seed(db_session, valor=1_000_000, dias=-3)
        # Alto valor pero no vencida
        _seed(db_session, valor=8_000_000, dias=5)
        # Cerrada
        _seed(
            db_session, valor=20_000_000, dias=-10,
            estado="LEVANTADA",
        )

        r = client.get(
            "/admin/glosas-altas-cuantia-vencidas?umbral=5000000"
        )
        d = r.json()
        assert d["total_red_flags"] == 1
        assert d["valor_total"] == 10_000_000
        assert d["items"][0]["dias_vencido"] == 5
