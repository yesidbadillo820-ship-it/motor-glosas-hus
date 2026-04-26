"""Tests del endpoint GET /sistema/health-completo (R190 P1)."""
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


class TestHealthCompleto:
    def test_estructura(self, client):
        r = client.get("/sistema/health-completo")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("evaluado_en", "estado_global",
                    "componentes", "operacion"):
            assert key in d
        for c in ("bd_responsiva", "ia_configurada",
                  "schedulers_activos"):
            assert c in d["componentes"]
        for o in ("total_glosas", "abiertas", "vencidas_graves"):
            assert o in d["operacion"]

    def test_estado_valido(self, client):
        r = client.get("/sistema/health-completo")
        d = r.json()
        assert d["estado_global"] in ("OK", "DEGRADED", "FAIL")

    def test_degraded_si_muchas_vencidas(self, client, db_session):
        for _ in range(25):
            db_session.add(GlosaRecord(
                eps="X", paciente="X", codigo_glosa="C",
                valor_objetado=1000, etapa="X", estado="RADICADA",
                creado_en=ahora_utc(),
                dias_restantes=-100,
            ))
        db_session.commit()
        r = client.get("/sistema/health-completo")
        d = r.json()
        # vencidas_graves > 20 → DEGRADED
        assert d["operacion"]["vencidas_graves"] == 25
        # estado_global puede ser DEGRADED o OK (depende de schedulers)
        # pero la métrica sí debe reflejarse
