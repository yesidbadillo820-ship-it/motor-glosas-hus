"""Tests del endpoint GET /sistema/health-score (R127 P1)."""
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


class TestHealthScore:
    def test_estructura(self, client):
        r = client.get("/sistema/health-score")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("score_total", "estado", "desglose", "evaluado_en"):
            assert key in d
        assert d["estado"] in ("HEALTHY", "DEGRADED", "UNHEALTHY")
        assert 0 <= d["score_total"] <= 100

    def test_desglose_tiene_5_componentes(self, client):
        r = client.get("/sistema/health-score")
        d = r.json()
        assert len(d["desglose"]) == 5
        nombres = {c["componente"] for c in d["desglose"]}
        assert "bd_responsiva" in nombres
        assert "schedulers_corriendo" in nombres
        assert "ia_disponible" in nombres
        assert "sin_alertas_criticas" in nombres
        assert "actividad_reciente" in nombres

    def test_componentes_tienen_peso_y_score(self, client):
        r = client.get("/sistema/health-score")
        d = r.json()
        # Pesos suman 100
        suma_pesos = sum(c["peso"] for c in d["desglose"])
        assert suma_pesos == 100
        for c in d["desglose"]:
            assert 0 <= c["score"] <= 100

    def test_alertas_criticas_baja_score(self, client, db_session):
        # Crear muchas glosas muy vencidas (>10 con dias_restantes<-30)
        for _ in range(15):
            db_session.add(GlosaRecord(
                eps="X", paciente="X", codigo_glosa="C",
                valor_objetado=1000, etapa="X", estado="RADICADA",
                creado_en=ahora_utc(),
                dias_restantes=-50,
            ))
        db_session.commit()

        r = client.get("/sistema/health-score")
        d = r.json()
        alertas = next(c for c in d["desglose"]
                       if c["componente"] == "sin_alertas_criticas")
        assert alertas["score"] == 0
