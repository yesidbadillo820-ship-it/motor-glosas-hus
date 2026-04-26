"""Tests del endpoint /sistema/resumen-mensual (R76 P1)."""
from __future__ import annotations

from datetime import datetime, timezone

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
    return UsuarioRecord(id=1, email="coord@hus.com", rol="COORDINADOR", activo=1)


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100_000, valor_aceptado=0,
        etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestResumenMensual:
    def test_estructura_respuesta(self, client):
        r = client.get("/sistema/resumen-mensual")
        assert r.status_code == 200
        d = r.json()
        for k in ("year", "month", "actual", "anterior",
                  "variacion_pct", "top_3_eps", "top_3_tipos",
                  "generado_en"):
            assert k in d

    def test_periodo_actual_default_es_mes_actual(self, client):
        r = client.get("/sistema/resumen-mensual")
        d = r.json()
        ahora = ahora_utc()
        assert d["year"] == ahora.year
        assert d["month"] == ahora.month

    def test_kpis_actual_correctos(self, client, db_session):
        ahora = ahora_utc()
        # 3 glosas en mes actual
        for vobj, vac in [(100_000, 0), (200_000, 50_000), (50_000, 0)]:
            _seed(db_session,
                  valor_objetado=vobj, valor_aceptado=vac,
                  creado_en=ahora.replace(day=15))
        r = client.get(f"/sistema/resumen-mensual?year={ahora.year}&month={ahora.month}")
        d = r.json()
        assert d["actual"]["count"] == 3
        assert d["actual"]["valor_objetado"] == 350_000
        assert d["actual"]["valor_aceptado"] == 50_000
        assert d["actual"]["valor_recuperado"] == 300_000

    def test_top_3_eps(self, client, db_session):
        ahora = ahora_utc()
        # FAMISANAR domina
        for _ in range(5):
            _seed(db_session, eps="FAMISANAR", valor_objetado=200_000,
                  creado_en=ahora.replace(day=10))
        _seed(db_session, eps="SALUD TOTAL", valor_objetado=50_000,
              creado_en=ahora.replace(day=10))
        r = client.get(f"/sistema/resumen-mensual?year={ahora.year}&month={ahora.month}")
        d = r.json()
        # Top debe ser FAMISANAR
        assert d["top_3_eps"][0]["eps"] == "FAMISANAR"

    def test_top_3_tipos(self, client, db_session):
        ahora = ahora_utc()
        for _ in range(4):
            _seed(db_session, codigo_glosa="TA0201", creado_en=ahora.replace(day=10))
        for _ in range(2):
            _seed(db_session, codigo_glosa="SO0101", creado_en=ahora.replace(day=10))
        r = client.get(f"/sistema/resumen-mensual?year={ahora.year}&month={ahora.month}")
        d = r.json()
        prefijos = [it["prefijo"] for it in d["top_3_tipos"]]
        assert prefijos[0] == "TA"
