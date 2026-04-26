"""Tests del endpoint GET /sistema/milestones (R150 P1)."""
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
def usuario_coord():
    return UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, valor_rec=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_recuperado=valor_rec,
        etapa="X", estado="LEVANTADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestMilestones:
    def test_estructura(self, client):
        r = client.get("/sistema/milestones")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("actual", "proximos_hitos"):
            assert key in d
        for key in ("total_glosas", "valor_recuperado_total",
                    "dias_en_operacion"):
            assert key in d["actual"]

    def test_sin_data(self, client):
        r = client.get("/sistema/milestones")
        d = r.json()
        assert d["actual"]["total_glosas"] == 0
        assert d["actual"]["valor_recuperado_total"] == 0

    def test_proximo_hito_glosas_100(self, client, db_session):
        # 47 glosas → próximo hito 100 (faltan 53)
        for _ in range(47):
            _seed(db_session)
        r = client.get("/sistema/milestones")
        d = r.json()
        assert d["proximos_hitos"]["glosas"]["siguiente"] == 100
        assert d["proximos_hitos"]["glosas"]["falta"] == 53

    def test_proximo_hito_valor(self, client, db_session):
        # $5M recuperado → próximo hito $10M
        _seed(db_session, valor_rec=5_000_000)
        r = client.get("/sistema/milestones")
        d = r.json()
        assert d["proximos_hitos"]["valor_recuperado"]["siguiente"] == 10_000_000
        assert d["proximos_hitos"]["valor_recuperado"]["falta"] == 5_000_000

    def test_dias_operacion(self, client, db_session):
        _seed(db_session)
        r = client.get("/sistema/milestones")
        d = r.json()
        # Glosa creada hoy → 0 días
        assert d["actual"]["dias_en_operacion"] is not None
        assert d["actual"]["dias_en_operacion"] >= 0
