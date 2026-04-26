"""Tests del endpoint GET /mi-desempeno/proximas-vencer (R66 P2)."""
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
def usuario():
    return UsuarioRecord(
        id=1, email="auditor@hus.com", nombre="Juan",
        rol="AUDITOR", activo=1,
    )


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="P", codigo_glosa="TA0201",
        valor_objetado=100, etapa="X", estado="RADICADA",
        dias_restantes=10, creado_en=ahora_utc(),
        auditor_email="auditor@hus.com",
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestProximasVencer:
    def test_sin_glosas(self, client):
        r = client.get("/mi-desempeno/proximas-vencer")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 0
        assert d["items"] == []

    def test_severidades_correctas(self, client, db_session):
        _seed(db_session, paciente="V", dias_restantes=-1)   # VENCIDA
        _seed(db_session, paciente="C", dias_restantes=1)    # CRITICA
        _seed(db_session, paciente="A", dias_restantes=4)    # ALTA
        _seed(db_session, paciente="M", dias_restantes=6)    # MEDIA
        r = client.get("/mi-desempeno/proximas-vencer?dias_limite=10")
        d = r.json()
        sevs = {it["paciente"]: it["severidad"] for it in d["items"]}
        assert sevs["V"] == "VENCIDA"
        assert sevs["C"] == "CRITICA"
        assert sevs["A"] == "ALTA"
        assert sevs["M"] == "MEDIA"
        assert d["vencidas"] == 1
        assert d["criticas"] == 1

    def test_excluye_estados_finales(self, client, db_session):
        """LEVANTADA/RATIFICADA/ACEPTADA no aparecen aunque tengan días."""
        _seed(db_session, paciente="ACT", dias_restantes=2, estado="RADICADA")
        _seed(db_session, paciente="LEVANTADA", dias_restantes=2, estado="LEVANTADA")
        _seed(db_session, paciente="ACEPTADA", dias_restantes=2, estado="ACEPTADA")
        r = client.get("/mi-desempeno/proximas-vencer?dias_limite=5")
        d = r.json()
        pacientes = [it["paciente"] for it in d["items"]]
        assert "ACT" in pacientes
        assert "LEVANTADA" not in pacientes
        assert "ACEPTADA" not in pacientes

    def test_orden_por_dias_asc(self, client, db_session):
        """Las más urgentes primero."""
        _seed(db_session, paciente="A", dias_restantes=5)
        _seed(db_session, paciente="B", dias_restantes=1)
        _seed(db_session, paciente="C", dias_restantes=3)
        r = client.get("/mi-desempeno/proximas-vencer?dias_limite=10")
        d = r.json()
        pacientes_ordenados = [it["paciente"] for it in d["items"]]
        assert pacientes_ordenados == ["B", "C", "A"]

    def test_solo_glosas_del_usuario(self, client, db_session):
        """Glosas asignadas a OTRO auditor NO aparecen."""
        _seed(db_session, paciente="MIA",
              auditor_email="auditor@hus.com", dias_restantes=2)
        _seed(db_session, paciente="OTRA",
              auditor_email="otro@hus.com", dias_restantes=2)
        r = client.get("/mi-desempeno/proximas-vencer")
        d = r.json()
        pacientes = [it["paciente"] for it in d["items"]]
        assert "MIA" in pacientes
        assert "OTRA" not in pacientes
