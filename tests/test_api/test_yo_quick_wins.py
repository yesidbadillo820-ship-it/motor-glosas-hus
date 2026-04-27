"""Tests del endpoint GET /usuarios/yo/quick-wins (R373 P1)."""
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


def _seed(db, eps, codigo, estado="RADICADA", gestor="Alice",
          valor=1000):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        fecha_decision_eps=(
            ahora_utc() if estado in (
                "LEVANTADA", "ACEPTADA", "RATIFICADA",
            ) else None
        ),
    ))
    db.commit()


class TestQuickWins:
    def test_detecta_par_alta_tasa(self, client, db_session):
        # Histórico (eps=X, codigo=C): 3 LEV / 3 → 100%
        for _ in range(3):
            _seed(db_session, "X", "C", estado="LEVANTADA")
        # Glosa abierta de Alice con ese par
        _seed(db_session, "X", "C", estado="RADICADA",
              gestor="Alice", valor=10000)

        r = client.get("/usuarios/yo/quick-wins")
        d = r.json()
        assert d["total_quick_wins"] == 1
        assert d["items"][0]["tasa_par_pct"] == 100.0
        assert d["items"][0]["valor_objetado"] == 10000

    def test_baja_tasa_excluida(self, client, db_session):
        # 1 LEV / 3 → 33%
        _seed(db_session, "Y", "D", estado="LEVANTADA")
        _seed(db_session, "Y", "D", estado="RATIFICADA")
        _seed(db_session, "Y", "D", estado="RATIFICADA")
        # Glosa abierta — no califica
        _seed(db_session, "Y", "D", estado="RADICADA",
              gestor="Alice")

        r = client.get("/usuarios/yo/quick-wins")
        d = r.json()
        assert d["total_quick_wins"] == 0

    def test_sin_muestras_excluida(self, client, db_session):
        _seed(db_session, "Z", "E", estado="RADICADA",
              gestor="Alice")
        r = client.get("/usuarios/yo/quick-wins")
        d = r.json()
        assert d["total_quick_wins"] == 0
