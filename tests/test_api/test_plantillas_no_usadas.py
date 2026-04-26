"""Tests del endpoint GET /plantillas-gold/no-usadas (R127 P2)."""
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
from app.models.db import PlantillaGoldRecord, UsuarioRecord


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


def _seed(db, titulo, usos=0, dias_atras_uso=None, activa=1):
    ult = (
        ahora_utc() - timedelta(days=dias_atras_uso)
        if dias_atras_uso is not None else None
    )
    db.add(PlantillaGoldRecord(
        eps="X", codigo_glosa="C", tipo="ARG",
        titulo=titulo, argumento="<p>X</p>",
        usos=usos, ultima_uso_en=ult, activa=activa,
    ))
    db.commit()


class TestPlantillasNoUsadas:
    def test_vacio(self, client):
        r = client.get("/plantillas-gold/no-usadas")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_nunca_usada(self, client, db_session):
        _seed(db_session, "Sin Usar", usos=0)
        r = client.get("/plantillas-gold/no-usadas")
        d = r.json()
        assert d["total_no_usadas"] == 1
        assert d["nunca_usadas"] == 1
        assert d["items"][0]["dias_sin_uso"] is None

    def test_uso_viejo(self, client, db_session):
        _seed(db_session, "Vieja", usos=10, dias_atras_uso=120)
        r = client.get("/plantillas-gold/no-usadas?dias=90")
        d = r.json()
        assert d["total_no_usadas"] == 1
        assert d["items"][0]["dias_sin_uso"] == 120

    def test_uso_reciente_no_aparece(self, client, db_session):
        _seed(db_session, "Activa", usos=10, dias_atras_uso=30)
        r = client.get("/plantillas-gold/no-usadas?dias=90")
        d = r.json()
        assert d["total_no_usadas"] == 0

    def test_excluye_inactivas(self, client, db_session):
        _seed(db_session, "Inactiva", usos=0, activa=0)
        r = client.get("/plantillas-gold/no-usadas")
        d = r.json()
        assert d["items"] == []

    def test_orden_mas_obsoletas_primero(self, client, db_session):
        _seed(db_session, "Vieja200", usos=5, dias_atras_uso=200)
        _seed(db_session, "Vieja100", usos=5, dias_atras_uso=100)
        _seed(db_session, "Nunca", usos=0)
        r = client.get("/plantillas-gold/no-usadas")
        d = r.json()
        # Vieja200 (200d) > Vieja100 (100d) > Nunca (null al final)
        assert d["items"][0]["titulo"] == "Vieja200"
        assert d["items"][1]["titulo"] == "Vieja100"
        assert d["items"][2]["titulo"] == "Nunca"
