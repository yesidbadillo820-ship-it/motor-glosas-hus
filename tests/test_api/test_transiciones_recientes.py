"""Tests del endpoint GET /glosas/stats/transiciones-recientes (R177 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


def _seed(db, ant, nuev, horas_atras=1):
    db.add(AuditLogRecord(
        usuario_email="u@x", accion="UPDATE",
        tabla="glosas", registro_id=1,
        campo="estado", valor_anterior=ant, valor_nuevo=nuev,
        timestamp=ahora_utc() - timedelta(hours=horas_atras),
    ))
    db.commit()


class TestTransicionesRecientes:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/transiciones-recientes")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_horas", "total_transiciones", "items"):
            assert key in d

    def test_agrupa_por_par(self, client, db_session):
        _seed(db_session, "RADICADA", "RESPONDIDA")
        _seed(db_session, "RADICADA", "RESPONDIDA")
        _seed(db_session, "RESPONDIDA", "LEVANTADA")

        r = client.get("/glosas/stats/transiciones-recientes")
        d = r.json()
        items = {(it["anterior"], it["nuevo"]): it for it in d["items"]}
        assert items[("RADICADA", "RESPONDIDA")]["count"] == 2
        assert items[("RESPONDIDA", "LEVANTADA")]["count"] == 1

    def test_orden_count_desc(self, client, db_session):
        for _ in range(3):
            _seed(db_session, "A", "B")
        for _ in range(1):
            _seed(db_session, "C", "D")
        r = client.get("/glosas/stats/transiciones-recientes")
        d = r.json()
        assert d["items"][0]["count"] == 3
        assert d["items"][1]["count"] == 1

    def test_excluye_otra_tabla(self, client, db_session):
        _seed(db_session, "X", "Y")  # tabla glosas
        # Audit en otra tabla
        db_session.add(AuditLogRecord(
            tabla="usuarios", registro_id=1, campo="estado",
            valor_anterior="A", valor_nuevo="B",
            timestamp=ahora_utc(),
        ))
        db_session.commit()
        r = client.get("/glosas/stats/transiciones-recientes")
        d = r.json()
        assert d["total_transiciones"] == 1
