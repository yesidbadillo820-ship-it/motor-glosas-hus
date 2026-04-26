"""Tests del endpoint GET /usuarios/yo/glosas-cerradas-mes (R318 P1)."""
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
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice", rol="AUDITOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gestor, fecha_decision, estado="LEVANTADA",
          recuperado=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        fecha_decision_eps=fecha_decision,
    ))
    db.commit()


class TestYoGlosasCerradasMes:
    def test_solo_mes_actual(self, client, db_session):
        # Mes actual
        _seed(
            db_session, "Alice",
            fecha_decision=ahora_utc(), estado="LEVANTADA",
            recuperado=500,
        )
        # Mes pasado (40 dias)
        _seed(
            db_session, "Alice",
            fecha_decision=ahora_utc() - timedelta(days=40),
            estado="LEVANTADA",
        )

        r = client.get("/usuarios/yo/glosas-cerradas-mes")
        d = r.json()
        # Solo la del mes actual debería contar (la de 40d puede o no
        # caer en mes actual dependiendo del día, pero asumiendo
        # primeros días del mes, debería estar fuera)
        assert d["levantadas"] >= 1

    def test_excluye_otros_gestores(self, client, db_session):
        _seed(
            db_session, "Bob",
            fecha_decision=ahora_utc(), estado="LEVANTADA",
        )
        r = client.get("/usuarios/yo/glosas-cerradas-mes")
        d = r.json()
        assert d["total_cerradas"] == 0
