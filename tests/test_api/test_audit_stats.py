"""Tests del endpoint GET /audit/stats (R87 P1)."""
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


def _seed(db, usuario, accion, tabla, dias_atras=0):
    db.add(AuditLogRecord(
        usuario_email=usuario, usuario_rol="AUDITOR",
        accion=accion, tabla=tabla,
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestAuditStats:
    def test_vacio(self, client):
        r = client.get("/audit/stats")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_eventos"] == 0
        assert d["top_10_usuarios"] == []
        assert d["top_10_acciones"] == []
        assert d["top_10_tablas"] == []
        assert d["eventos_por_dia"] == []

    def test_total_y_top_usuarios(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "alice@x", "UPDATE", "glosas")
        for _ in range(2):
            _seed(db_session, "bob@x", "DELETE", "glosas")
        r = client.get("/audit/stats")
        d = r.json()
        assert d["total_eventos"] == 7
        # alice debe ir primero (5 vs 2)
        assert d["top_10_usuarios"][0] == {"usuario": "alice@x", "eventos": 5}
        assert d["top_10_usuarios"][1] == {"usuario": "bob@x", "eventos": 2}

    def test_top_acciones_y_tablas(self, client, db_session):
        _seed(db_session, "u1@x", "CREATE", "glosas")
        _seed(db_session, "u1@x", "CREATE", "usuarios")
        _seed(db_session, "u1@x", "UPDATE", "glosas")
        _seed(db_session, "u1@x", "UPDATE", "glosas")
        r = client.get("/audit/stats")
        d = r.json()
        # UPDATE = 2, CREATE = 2 — ambos deben estar presentes
        acciones = {it["accion"]: it["eventos"] for it in d["top_10_acciones"]}
        assert acciones == {"UPDATE": 2, "CREATE": 2}
        tablas = {it["tabla"]: it["eventos"] for it in d["top_10_tablas"]}
        assert tablas == {"glosas": 3, "usuarios": 1}

    def test_ventana_filtra_fuera_de_rango(self, client, db_session):
        _seed(db_session, "u1@x", "X", "T", dias_atras=5)   # dentro (default 30)
        _seed(db_session, "u2@x", "X", "T", dias_atras=60)  # fuera
        r = client.get("/audit/stats")
        d = r.json()
        assert d["total_eventos"] == 1
        assert d["top_10_usuarios"] == [{"usuario": "u1@x", "eventos": 1}]

    def test_ventana_custom_dias_7(self, client, db_session):
        _seed(db_session, "u1@x", "X", "T", dias_atras=3)
        _seed(db_session, "u2@x", "X", "T", dias_atras=15)  # fuera con dias=7
        r = client.get("/audit/stats?dias=7")
        d = r.json()
        assert d["ventana_dias"] == 7
        assert d["total_eventos"] == 1

    def test_eventos_por_dia_ordenado(self, client, db_session):
        _seed(db_session, "u1@x", "X", "T", dias_atras=0)
        _seed(db_session, "u1@x", "X", "T", dias_atras=0)
        _seed(db_session, "u1@x", "X", "T", dias_atras=2)
        r = client.get("/audit/stats")
        d = r.json()
        # 2 días distintos
        assert len(d["eventos_por_dia"]) == 2
        # Suma cuadra
        assert sum(it["eventos"] for it in d["eventos_por_dia"]) == 3
        # Ordenado ascendente
        fechas = [it["fecha"] for it in d["eventos_por_dia"]]
        assert fechas == sorted(fechas)
