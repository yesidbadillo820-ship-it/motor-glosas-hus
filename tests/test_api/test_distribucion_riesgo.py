"""Tests del endpoint GET /glosas/stats/distribucion-riesgo (R139 P1)."""
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestDistribucionRiesgo:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/distribucion-riesgo")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_glosas_abiertas", "valor_pendiente_total",
                    "matriz"):
            assert key in d
        # 4 urgencias × 3 montos = 12 celdas
        assert len(d["matriz"]) == 12

    def test_clasifica_celda_correcta(self, client, db_session):
        # VENCIDA + ALTO ($10M)
        _seed(db_session, dias_restantes=-5, valor_objetado=10_000_000)
        # CRITICA + BAJO ($500k)
        _seed(db_session, dias_restantes=2, valor_objetado=500_000)

        r = client.get("/glosas/stats/distribucion-riesgo")
        d = r.json()
        venc_alto = next(
            it for it in d["matriz"]
            if it["urgencia"] == "VENCIDA" and it["monto"] == "ALTO"
        )
        crit_bajo = next(
            it for it in d["matriz"]
            if it["urgencia"] == "CRITICA" and it["monto"] == "BAJO"
        )
        assert venc_alto["count"] == 1
        assert venc_alto["valor_total"] == 10_000_000
        assert crit_bajo["count"] == 1
        assert crit_bajo["valor_total"] == 500_000

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, estado="LEVANTADA",
              dias_restantes=-100, valor_objetado=99_999_999)
        r = client.get("/glosas/stats/distribucion-riesgo")
        d = r.json()
        assert d["total_glosas_abiertas"] == 0

    def test_pct_consistente(self, client, db_session):
        # 1 vencida + 1 lejana
        _seed(db_session, dias_restantes=-5, valor_objetado=8_000_000)
        _seed(db_session, dias_restantes=20, valor_objetado=2_000_000)
        r = client.get("/glosas/stats/distribucion-riesgo")
        d = r.json()
        # cada celda con datos: 50% count
        celdas_con_datos = [it for it in d["matriz"] if it["count"] > 0]
        assert len(celdas_con_datos) == 2
        pct_total = sum(it["pct_count"] for it in celdas_con_datos)
        assert abs(pct_total - 100.0) < 0.5

    def test_orden_por_valor_desc(self, client, db_session):
        _seed(db_session, dias_restantes=-5, valor_objetado=10_000_000)
        _seed(db_session, dias_restantes=2, valor_objetado=500_000)
        r = client.get("/glosas/stats/distribucion-riesgo")
        d = r.json()
        # La primera celda no-vacía debe tener más valor que la segunda
        valores = [it["valor_total"] for it in d["matriz"]]
        assert valores == sorted(valores, reverse=True)
