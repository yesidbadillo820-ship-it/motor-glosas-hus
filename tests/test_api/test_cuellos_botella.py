"""Tests del endpoint GET /glosas/stats/cuellos-botella (R135 P1)."""
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


def _seed_audit(db, gid, anterior, nuevo, dias_atras):
    db.add(AuditLogRecord(
        usuario_email="u@x", accion="UPDATE",
        tabla="glosas", registro_id=gid,
        campo="estado", valor_anterior=anterior, valor_nuevo=nuevo,
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestCuellosBotella:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/cuellos-botella")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_calcula_tiempo_entre_transiciones(self, client, db_session):
        # Glosa 1: RADICADA por 10 días, luego pasa a RESPONDIDA
        _seed_audit(db_session, 1, None, "RADICADA", dias_atras=20)
        _seed_audit(db_session, 1, "RADICADA", "RESPONDIDA",
                    dias_atras=10)
        # Glosa 2: RADICADA por 5 días
        _seed_audit(db_session, 2, None, "RADICADA", dias_atras=15)
        _seed_audit(db_session, 2, "RADICADA", "RESPONDIDA",
                    dias_atras=10)

        r = client.get("/glosas/stats/cuellos-botella")
        d = r.json()
        radicada = next(it for it in d["items"]
                        if it["estado"] == "RADICADA")
        # Tiempos: 10d y 5d → promedio 7.5d
        assert radicada["count_glosas_con_transicion"] == 2
        assert 7 <= radicada["tiempo_promedio_dias"] <= 8

    def test_orden_por_tiempo_desc(self, client, db_session):
        # ESTADO_LENTO: 30d → debe ir primero
        _seed_audit(db_session, 1, None, "ESTADO_LENTO", dias_atras=40)
        _seed_audit(db_session, 1, "ESTADO_LENTO", "X", dias_atras=10)
        # ESTADO_RAPIDO: 1d → debe ir después
        _seed_audit(db_session, 2, None, "ESTADO_RAPIDO", dias_atras=11)
        _seed_audit(db_session, 2, "ESTADO_RAPIDO", "Y", dias_atras=10)

        r = client.get("/glosas/stats/cuellos-botella")
        d = r.json()
        assert d["items"][0]["estado"] == "ESTADO_LENTO"
        assert d["items"][1]["estado"] == "ESTADO_RAPIDO"

    def test_excluye_otra_tabla(self, client, db_session):
        _seed_audit(db_session, 1, None, "X", dias_atras=10)
        _seed_audit(db_session, 1, "X", "Y", dias_atras=5)
        # Audit en otra tabla
        db_session.add(AuditLogRecord(
            tabla="usuarios", registro_id=1, campo="estado",
            valor_anterior="X", timestamp=ahora_utc(),
        ))
        db_session.commit()

        r = client.get("/glosas/stats/cuellos-botella")
        d = r.json()
        # Solo 1 transición de glosa, no contagia con la de usuarios
        assert sum(it["count_glosas_con_transicion"] for it in d["items"]) == 1
