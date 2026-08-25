"""Tests del endpoint GET /glosas/stats/historicos-ganadores (feature #3)."""

from __future__ import annotations

from datetime import timedelta

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
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(
    db,
    *,
    eps,
    codigo,
    estado,
    dictamen,
    dias_atras=0,
    valor_recuperado=0.0,
    valor_objetado=0.0,
):
    db.add(
        GlosaRecord(
            eps=eps,
            paciente="P",
            codigo_glosa=codigo,
            valor_objetado=valor_objetado,
            etapa="X",
            estado=estado,
            creado_en=ahora_utc(),
            dictamen=dictamen,
            valor_recuperado=valor_recuperado,
            fecha_decision_eps=ahora_utc() - timedelta(days=dias_atras),
        )
    )
    db.commit()


class TestHistoricosGanadores:
    def test_devuelve_levantadas_mismo_par(self, client, db_session):
        # 3 LEVANTADAS del mismo (eps, codigo) + 1 RATIFICADA + 1 distinto código
        for i in range(3):
            _seed(
                db_session,
                eps="FAMISANAR",
                codigo="TA0201",
                estado="LEVANTADA",
                dictamen=f"DICT-W-{i}",
                dias_atras=i,
                valor_recuperado=100_000.0 * (i + 1),
            )
        _seed(
            db_session,
            eps="FAMISANAR",
            codigo="TA0201",
            estado="RATIFICADA",
            dictamen="DICT-LOST",
        )
        _seed(
            db_session,
            eps="FAMISANAR",
            codigo="CO0101",
            estado="LEVANTADA",
            dictamen="DICT-OTHER-CODE",
        )

        r = client.get("/glosas/stats/historicos-ganadores?eps=FAMISANAR&codigo=TA0201&limit=3")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 3
        assert all(item["dictamen"].startswith("DICT-W-") for item in d["items"])
        # ordenados por fecha_decision_eps desc → el más reciente (i=0) primero
        assert d["items"][0]["dictamen"] == "DICT-W-0"
        assert d["valor_recuperado_total"] == 100_000 + 200_000 + 300_000

    def test_no_match_devuelve_vacio(self, client):
        r = client.get("/glosas/stats/historicos-ganadores?eps=SIN_GLOSAS&codigo=XX9999")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 0
        assert d["items"] == []

    def test_limit_acotado(self, client, db_session):
        for i in range(15):
            _seed(
                db_session,
                eps="FAMISANAR",
                codigo="TA0201",
                estado="LEVANTADA",
                dictamen=f"D{i}",
                dias_atras=i,
            )
        # limit > 10 se acota a 10
        r = client.get("/glosas/stats/historicos-ganadores?eps=FAMISANAR&codigo=TA0201&limit=99")
        assert len(r.json()["items"]) == 10

    def test_eps_case_insensitive(self, client, db_session):
        _seed(
            db_session,
            eps="FAMISANAR EPS",
            codigo="TA0201",
            estado="LEVANTADA",
            dictamen="D",
        )
        r = client.get("/glosas/stats/historicos-ganadores?eps=famisanar eps&codigo=TA0201")
        assert r.json()["total"] == 1

    def test_eps_o_codigo_vacios_devuelve_razon(self, client):
        r = client.get("/glosas/stats/historicos-ganadores?eps=&codigo=")
        d = r.json()
        assert d["total"] == 0
        assert "razon" in d
