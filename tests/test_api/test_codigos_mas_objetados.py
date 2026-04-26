"""Tests del endpoint GET /glosas/stats/codigos-mas-objetados (R102 P1)."""
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


def _seed(db, codigo, eps="X", estado="RADICADA", valor=1000):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestCodigosMasObjetados:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/codigos-mas-objetados")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_codigos_unicos"] == 0
        assert d["items"] == []

    def test_orden_por_frecuencia_desc(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "TA0201")
        for _ in range(2):
            _seed(db_session, "FA0603")
        for _ in range(1):
            _seed(db_session, "AU0801")

        r = client.get("/glosas/stats/codigos-mas-objetados")
        d = r.json()
        codigos = [it["codigo"] for it in d["items"]]
        assert codigos == ["TA0201", "FA0603", "AU0801"]
        assert d["items"][0]["frecuencia"] == 5

    def test_tasa_levantamiento(self, client, db_session):
        _seed(db_session, "TA0201", estado="LEVANTADA")
        _seed(db_session, "TA0201", estado="LEVANTADA")
        _seed(db_session, "TA0201", estado="ACEPTADA")
        _seed(db_session, "TA0201", estado="RADICADA")  # pendiente, no decidida

        r = client.get("/glosas/stats/codigos-mas-objetados")
        d = r.json()
        item = next(it for it in d["items"] if it["codigo"] == "TA0201")
        # 2 levantadas / 3 decididas = 66.67%
        assert item["tasa_levantamiento_pct"] == 66.67

    def test_eps_principales(self, client, db_session):
        for _ in range(3):
            _seed(db_session, "TA0201", eps="SANITAS")
        for _ in range(2):
            _seed(db_session, "TA0201", eps="NUEVA EPS")
        _seed(db_session, "TA0201", eps="OTRA")

        r = client.get("/glosas/stats/codigos-mas-objetados")
        d = r.json()
        item = d["items"][0]
        # Top 3 EPS, ordenado DESC
        eps_list = [e["eps"] for e in item["eps_principales"]]
        assert eps_list == ["SANITAS", "NUEVA EPS", "OTRA"]

    def test_top_limita_resultados(self, client, db_session):
        # 5 códigos distintos, top=2
        for c in ["A", "B", "C", "D", "E"]:
            _seed(db_session, c)
        r = client.get("/glosas/stats/codigos-mas-objetados?top=2")
        d = r.json()
        assert len(d["items"]) == 2
        assert d["total_codigos_unicos"] == 5
