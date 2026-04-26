"""Tests del endpoint GET /plantillas-gold/efectividad (R107 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, PlantillaGoldRecord, UsuarioRecord


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


def _seed_glosa(db, estado="LEVANTADA", valor_rec=10000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=10000, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


def _seed_plantilla(db, titulo, usos=0, glosa_origen_id=None, activa=1):
    db.add(PlantillaGoldRecord(
        eps="X", codigo_glosa="C", tipo="ARG",
        titulo=titulo, argumento="<p>argumento</p>",
        usos=usos, glosa_origen_id=glosa_origen_id,
        activa=activa,
    ))
    db.commit()


class TestPlantillasEfectividad:
    def test_vacio(self, client):
        r = client.get("/plantillas-gold/efectividad")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []
        assert d["gold_reales"] == 0

    def test_filtra_min_usos(self, client, db_session):
        _seed_plantilla(db_session, "P1", usos=5)
        _seed_plantilla(db_session, "P2", usos=0)
        r = client.get("/plantillas-gold/efectividad?min_usos=1")
        d = r.json()
        titulos = [it["titulo"] for it in d["items"]]
        assert "P1" in titulos
        assert "P2" not in titulos

    def test_excluye_inactivas(self, client, db_session):
        _seed_plantilla(db_session, "Activa", usos=3, activa=1)
        _seed_plantilla(db_session, "Inactiva", usos=10, activa=0)
        r = client.get("/plantillas-gold/efectividad")
        d = r.json()
        titulos = [it["titulo"] for it in d["items"]]
        assert "Activa" in titulos
        assert "Inactiva" not in titulos

    def test_es_gold_real(self, client, db_session):
        # Glosa origen LEVANTADA + plantilla con 5 usos → es_gold_real=True
        g = _seed_glosa(db_session, "LEVANTADA")
        _seed_plantilla(db_session, "Real", usos=5, glosa_origen_id=g.id)
        # Plantilla con muchos usos pero glosa origen ACEPTADA → no es gold
        g2 = _seed_glosa(db_session, "ACEPTADA")
        _seed_plantilla(db_session, "FalsaGold", usos=10,
                        glosa_origen_id=g2.id)
        # Plantilla LEVANTADA pero solo 1 uso → no llega al threshold de 3
        g3 = _seed_glosa(db_session, "LEVANTADA")
        _seed_plantilla(db_session, "Pocos", usos=1, glosa_origen_id=g3.id)

        r = client.get("/plantillas-gold/efectividad")
        d = r.json()
        items = {it["titulo"]: it for it in d["items"]}
        assert items["Real"]["es_gold_real"] is True
        assert items["FalsaGold"]["es_gold_real"] is False
        assert items["Pocos"]["es_gold_real"] is False
        assert d["gold_reales"] == 1

    def test_orden_por_usos_desc(self, client, db_session):
        _seed_plantilla(db_session, "Pop", usos=20)
        _seed_plantilla(db_session, "Med", usos=10)
        _seed_plantilla(db_session, "Bajo", usos=2)
        r = client.get("/plantillas-gold/efectividad")
        d = r.json()
        usos = [it["usos"] for it in d["items"]]
        assert usos == sorted(usos, reverse=True)
