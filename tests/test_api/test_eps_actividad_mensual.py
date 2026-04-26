"""Tests del endpoint GET /glosas/stats/eps-actividad-mensual (R181 P1)."""
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


def _seed(db, eps, fecha, valor_obj=1000, valor_rec=0):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor_obj, valor_recuperado=valor_rec,
        etapa="X", estado="RADICADA",
        creado_en=fecha,
    ))
    db.commit()


class TestEPSActividadMensual:
    def test_estructura(self, client):
        r = client.get(
            "/glosas/stats/eps-actividad-mensual?eps=SANITAS"
        )
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("eps", "meses_solicitados",
                    "total_meses_disponibles", "serie"):
            assert key in d
        assert d["eps"] == "SANITAS"

    def test_serie_basica(self, client, db_session):
        _seed(db_session, "SANITAS",
              datetime(2026, 4, 5, tzinfo=timezone.utc),
              valor_obj=10_000, valor_rec=5_000)
        _seed(db_session, "SANITAS",
              datetime(2026, 4, 20, tzinfo=timezone.utc),
              valor_obj=20_000)
        _seed(db_session, "SANITAS",
              datetime(2026, 3, 1, tzinfo=timezone.utc),
              valor_obj=5_000)

        r = client.get(
            "/glosas/stats/eps-actividad-mensual?eps=SANITAS&meses=24"
        )
        d = r.json()
        meses = {s["mes"]: s for s in d["serie"]}
        assert meses["2026-04"]["glosas_iniciadas"] == 2
        assert meses["2026-04"]["valor_objetado"] == 30_000
        assert meses["2026-04"]["valor_recuperado"] == 5_000
        assert meses["2026-03"]["glosas_iniciadas"] == 1

    def test_aislamiento_por_eps(self, client, db_session):
        _seed(db_session, "SANITAS",
              datetime(2026, 4, 5, tzinfo=timezone.utc))
        _seed(db_session, "OTRA",
              datetime(2026, 4, 5, tzinfo=timezone.utc))

        r = client.get(
            "/glosas/stats/eps-actividad-mensual?eps=SANITAS&meses=24"
        )
        d = r.json()
        # Solo 1 mes con 1 glosa de SANITAS
        assert d["serie"][0]["glosas_iniciadas"] == 1
