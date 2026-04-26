"""Tests del endpoint /glosas/stats/tendencia-diaria (R72 P1)."""
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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100_000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
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


class TestTendenciaDiaria:
    def test_sin_glosas_serie_completa_ceros(self, client):
        r = client.get("/glosas/stats/tendencia-diaria?dias=7")
        assert r.status_code == 200
        d = r.json()
        # Aún sin glosas, la serie tiene 7-8 días con count=0
        assert d["total_glosas"] == 0
        # Cada item tiene fecha y count
        for s in d["serie"]:
            assert "fecha" in s
            assert s["count"] == 0

    def test_glosas_aparecen_en_fecha_correcta(self, client, db_session):
        hoy = ahora_utc()
        _seed(db_session, creado_en=hoy)
        _seed(db_session, creado_en=hoy)
        _seed(db_session, creado_en=hoy - timedelta(days=2))
        r = client.get("/glosas/stats/tendencia-diaria?dias=7")
        d = r.json()
        # total = 3
        assert d["total_glosas"] == 3
        # Fecha de hoy debe tener count >= 2
        fecha_hoy_iso = hoy.date().isoformat()
        items_hoy = [s for s in d["serie"] if s["fecha"] == fecha_hoy_iso]
        assert len(items_hoy) == 1
        assert items_hoy[0]["count"] >= 2

    def test_serie_continua_sin_huecos(self, client, db_session):
        """Días sin glosas deben aparecer con count=0 (no faltar)."""
        _seed(db_session, creado_en=ahora_utc() - timedelta(days=5))
        # Sin glosas en los otros 6 días
        r = client.get("/glosas/stats/tendencia-diaria?dias=10")
        d = r.json()
        # Todas las fechas presentes
        fechas = [s["fecha"] for s in d["serie"]]
        # Conjunto único
        assert len(fechas) == len(set(fechas))
        # Al menos un día tiene count=1, los demás 0
        assert sum(1 for s in d["serie"] if s["count"] == 0) >= 5

    def test_valor_total_acumulado(self, client, db_session):
        _seed(db_session, valor_objetado=100_000)
        _seed(db_session, valor_objetado=200_000)
        _seed(db_session, valor_objetado=50_000)
        r = client.get("/glosas/stats/tendencia-diaria?dias=7")
        d = r.json()
        assert d["valor_total"] == 350_000

    def test_filtro_ventana(self, client, db_session):
        """Glosas fuera de la ventana NO deben aparecer."""
        _seed(db_session, creado_en=ahora_utc() - timedelta(days=60))
        _seed(db_session, creado_en=ahora_utc())
        r = client.get("/glosas/stats/tendencia-diaria?dias=7")
        d = r.json()
        # Solo la reciente cuenta
        assert d["total_glosas"] == 1
