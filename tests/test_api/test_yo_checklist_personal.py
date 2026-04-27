"""Tests del endpoint GET /usuarios/yo/checklist-personal (R381 P1)."""
from __future__ import annotations

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


def _seed(db, gestor="Alice", estado="RADICADA", dictamen=None,
          dias=10, valor=1000, codigo_respuesta=None,
          valor_aceptado=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, valor_aceptado=valor_aceptado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dictamen=dictamen,
        dias_restantes=dias,
        codigo_respuesta=codigo_respuesta,
    ))
    db.commit()


class TestChecklistPersonal:
    def test_detecta_pendientes(self, client, db_session):
        # Sin dictamen + alto valor + crítica
        _seed(db_session, valor=10_000_000, dias=2)
        # Dictamen corto
        _seed(db_session, dictamen="ok")
        # Vencida
        _seed(db_session, dias=-5, dictamen="x" * 200)
        # RESPONDIDA sin código respuesta
        _seed(db_session, estado="RESPONDIDA",
              dictamen="x" * 200)

        r = client.get("/usuarios/yo/checklist-personal")
        d = r.json()
        ids = {it["id"] for it in d["items"]}
        assert "sin_dictamen" in ids
        assert "dictamen_corto" in ids
        assert "vencidas" in ids
        assert "criticas" in ids
        assert "alto_valor_sin_dictamen" in ids
        assert "sin_codigo_respuesta" in ids
        # Prioridad 1 va primero
        assert d["items"][0]["prioridad"] == 1

    def test_sin_pendientes(self, client):
        r = client.get("/usuarios/yo/checklist-personal")
        d = r.json()
        assert d["total_pendientes"] == 0
        assert d["items"] == []
