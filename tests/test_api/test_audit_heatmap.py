"""Tests del endpoint GET /audit/heatmap-actividad (R159 P1)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AuditLogRecord, UsuarioRecord


def _lunes_pasado():
    """Lunes de la semana pasada (7-13 días atrás), a las 00:00.

    Se usa en vez de una fecha fija para que los tests no caduquen cuando esa
    fecha se sale de la ventana de días que consulta el endpoint.
    """
    ahora = ahora_utc()
    return (ahora - timedelta(days=ahora.weekday() + 7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


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
def usuario_coord(db_session):
    u = UsuarioRecord(
        id=1,
        email="coord@hus.gov.co",
        rol="COORDINADOR",
        activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, ts):
    db.add(
        AuditLogRecord(
            usuario_email="u@x",
            accion="X",
            tabla="T",
            timestamp=ts,
        )
    )
    db.commit()


class TestAuditHeatmap:
    def test_estructura(self, client):
        r = client.get("/audit/heatmap-actividad")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "total_eventos", "items"):
            assert key in d

    def test_clasifica_dia_hora(self, client, db_session):
        # Fechas relativas (lunes de la semana pasada) para que no caduquen
        # al salirse de la ventana de días que consulta el endpoint.
        lunes = _lunes_pasado()
        # Lunes (weekday=0), 10am
        _seed(db_session, lunes.replace(hour=10, minute=0))
        _seed(db_session, lunes.replace(hour=10, minute=30))
        # Miércoles (weekday=2), 14h
        _seed(db_session, (lunes + timedelta(days=2)).replace(hour=14, minute=5))

        r = client.get("/audit/heatmap-actividad?dias=120")
        d = r.json()
        items = {(it["dia_semana"], it["hora"]): it for it in d["items"]}
        assert items[(0, 10)]["count"] == 2
        assert items[(0, 10)]["dia_nombre"] == "Lunes"
        assert items[(2, 14)]["count"] == 1

    def test_orden_dia_hora(self, client, db_session):
        lunes = _lunes_pasado()
        _seed(db_session, lunes.replace(hour=10, minute=0))
        _seed(db_session, (lunes + timedelta(days=2)).replace(hour=14, minute=0))
        r = client.get("/audit/heatmap-actividad?dias=120")
        d = r.json()
        keys = [(it["dia_semana"], it["hora"]) for it in d["items"]]
        assert keys == sorted(keys)
