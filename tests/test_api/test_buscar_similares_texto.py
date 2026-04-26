"""Tests del endpoint GET /glosas/buscar-similares-texto (R103 P2)."""
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


def _seed(db, texto):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        texto_glosa_original=texto,
    ))
    db.commit()


class TestBuscarSimilaresTexto:
    def test_query_corta_400(self, client):
        r = client.get("/glosas/buscar-similares-texto?texto=hola")
        assert r.status_code == 422  # FastAPI valida min_length

    def test_sin_candidatas(self, client):
        r = client.get(
            "/glosas/buscar-similares-texto"
            "?texto=insumos hospitalarios farmaceuticos"
        )
        d = r.json()
        assert d["total_evaluadas"] == 0
        assert d["items"] == []

    def test_encuentra_similares(self, client, db_session):
        _seed(db_session, "insumos farmaceuticos administrados al paciente")
        _seed(db_session, "honorarios medicos por consulta especializada")
        _seed(db_session,
              "insumos quirurgicos consumidos durante intervencion")

        r = client.get(
            "/glosas/buscar-similares-texto"
            "?texto=insumos administrados durante hospitalizacion"
        )
        d = r.json()
        # Las 2 con "insumos" deben aparecer; los honorarios médicos no
        assert d["total_con_score_minimo"] >= 2
        textos = [it["preview"] for it in d["items"]]
        # Las que tienen "insumos" rankean primero
        assert any("insumos" in t for t in textos[:2])

    def test_score_idempotente_glosa_identica(self, client, db_session):
        texto = "valor cobrado supera tarifa contratada"
        _seed(db_session, texto)
        r = client.get(
            f"/glosas/buscar-similares-texto?texto={texto}"
        )
        d = r.json()
        # Match exacto → score 1.0
        assert d["items"][0]["score_similitud"] == 1.0

    def test_top_limita(self, client, db_session):
        for _ in range(15):
            _seed(db_session, "insumos farmaceuticos administrados paciente")
        r = client.get(
            "/glosas/buscar-similares-texto?texto=insumos farmaceuticos&top=5"
        )
        d = r.json()
        assert len(d["items"]) == 5
