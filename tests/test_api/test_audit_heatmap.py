"""Tests del endpoint GET /audit/heatmap-actividad (R159 P1)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AuditLogRecord, UsuarioRecord


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
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
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
    db.add(AuditLogRecord(
        usuario_email="u@x", accion="X", tabla="T",
        timestamp=ts,
    ))
    db.commit()


class TestAuditHeatmap:
    def test_estructura(self, client):
        r = client.get("/audit/heatmap-actividad")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "total_eventos", "items"):
            assert key in d

    def test_clasifica_dia_hora(self, client, db_session):
        # 2026-04-20 fue Lunes (weekday=0), 10am
        _seed(db_session, datetime(2026, 4, 20, 10, 0,
                                   tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 4, 20, 10, 30,
                                   tzinfo=timezone.utc))
        # 2026-04-22 fue Miércoles (weekday=2), 14h
        _seed(db_session, datetime(2026, 4, 22, 14, 5,
                                   tzinfo=timezone.utc))

        r = client.get("/audit/heatmap-actividad?dias=120")
        d = r.json()
        items = {(it["dia_semana"], it["hora"]): it for it in d["items"]}
        assert items[(0, 10)]["count"] == 2
        assert items[(0, 10)]["dia_nombre"] == "Lunes"
        assert items[(2, 14)]["count"] == 1

    def test_orden_dia_hora(self, client, db_session):
        _seed(db_session, datetime(2026, 4, 20, 10, 0,
                                   tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 4, 22, 14, 0,
                                   tzinfo=timezone.utc))
        r = client.get("/audit/heatmap-actividad?dias=120")
        d = r.json()
        keys = [(it["dia_semana"], it["hora"]) for it in d["items"]]
        assert keys == sorted(keys)
