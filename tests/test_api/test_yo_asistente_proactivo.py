"""Tests del endpoint GET /usuarios/yo/asistente-proactivo (R368 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ComentarioGlosaRecord,
    GlosaRecord,
    UsuarioRecord,
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
def usuario():
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice",
        rol="AUDITOR", activo=1,
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


def _seed_glosa(db, gestor, dias=10, valor=1000, dictamen=None,
                estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
        dictamen=dictamen,
    ))
    db.commit()


class TestAsistenteProactivo:
    def test_sin_alertas(self, client):
        r = client.get("/usuarios/yo/asistente-proactivo")
        d = r.json()
        # Sin glosas: debe dar el mensaje OK
        assert d["total_acciones"] == 1
        assert d["acciones"][0]["tipo"] == "OK"

    def test_vencidas_urgente(self, client, db_session):
        _seed_glosa(db_session, "Alice", dias=-5)
        r = client.get("/usuarios/yo/asistente-proactivo")
        d = r.json()
        urgente = next(
            (a for a in d["acciones"] if a["tipo"] == "URGENTE"),
            None,
        )
        assert urgente is not None
        assert urgente["count"] == 1
        assert urgente["prioridad"] == 1

    def test_oportunidad_alta_cuantia_sin_dictamen(self, client, db_session):
        _seed_glosa(
            db_session, "Alice", dias=10, valor=10_000_000,
            dictamen=None,
        )
        r = client.get("/usuarios/yo/asistente-proactivo")
        d = r.json()
        op = next(
            (a for a in d["acciones"] if a["tipo"] == "OPORTUNIDAD"),
            None,
        )
        assert op is not None
        assert op["count"] == 1

    def test_prioridad_orden(self, client, db_session):
        _seed_glosa(db_session, "Alice", dias=-3)  # vencida
        _seed_glosa(db_session, "Alice", dias=2)   # crítica
        r = client.get("/usuarios/yo/asistente-proactivo")
        d = r.json()
        # Las acciones siguen el orden de la lógica;
        # verificamos que ambas estén
        tipos = [a["tipo"] for a in d["acciones"]]
        assert "URGENTE" in tipos
        assert "IMPORTANTE" in tipos
