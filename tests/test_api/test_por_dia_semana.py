"""Tests del endpoint GET /glosas/stats/por-dia-semana (R141 P2)."""

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


def _seed(db, fecha):
    db.add(
        GlosaRecord(
            eps="X",
            paciente="X",
            codigo_glosa="C",
            valor_objetado=1000,
            etapa="X",
            estado="RADICADA",
            creado_en=fecha,
        )
    )
    db.commit()


def _lunes_pasado():
    """Lunes de la semana pasada 10:00 UTC — siempre dentro de la ventana de 90d.

    Con fechas fijas el test explotaba cuando la fecha quedaba a más de 90
    días de "hoy" (ventana default del endpoint).
    """
    hoy = ahora_utc()
    lunes = hoy - timedelta(days=hoy.weekday() + 7)
    return lunes.replace(hour=10, minute=0, second=0, microsecond=0)


class TestPorDiaSemana:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/por-dia-semana")
        assert r.status_code == 200, r.text
        d = r.json()
        # 7 días siempre presentes (incluso si están en 0)
        assert len(d["items"]) == 7
        assert d["items"][0]["dia"] == "Lunes"
        assert d["items"][6]["dia"] == "Domingo"

    def test_clasifica_por_dia(self, client, db_session):
        lunes = _lunes_pasado()
        _seed(db_session, lunes)
        _seed(db_session, lunes.replace(hour=11))
        # Miércoles de esa misma semana
        _seed(db_session, lunes + timedelta(days=2))

        r = client.get("/glosas/stats/por-dia-semana")
        d = r.json()
        items = {it["dia"]: it for it in d["items"]}
        assert items["Lunes"]["count"] == 2
        assert items["Miércoles"]["count"] == 1
        assert d["total_glosas"] == 3

    def test_pct_del_total(self, client, db_session):
        lunes = _lunes_pasado()
        # 4 glosas el lunes
        for _ in range(4):
            _seed(db_session, lunes)
        # 1 glosa el martes
        _seed(db_session, lunes + timedelta(days=1))

        r = client.get("/glosas/stats/por-dia-semana")
        d = r.json()
        items = {it["dia"]: it for it in d["items"]}
        assert items["Lunes"]["pct_del_total"] == 80.0
        assert items["Martes"]["pct_del_total"] == 20.0

    def test_excluye_fuera_ventana(self, client, db_session):
        from datetime import timedelta

        ahora = ahora_utc()
        # Reciente
        _seed(db_session, ahora - timedelta(days=10))
        # Fuera de ventana (default 90d)
        _seed(db_session, ahora - timedelta(days=200))

        r = client.get("/glosas/stats/por-dia-semana")
        d = r.json()
        assert d["total_glosas"] == 1
