"""Tests del endpoint GET /admin/incidentes-criticos (R162 P1)."""
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
from app.models.db import (
    ConciliacionRecord, GlosaRecord, PlantillaGoldRecord, UsuarioRecord,
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
def usuario_super(db_session):
    u = UsuarioRecord(
        id=1, email="root@hus.gov.co", rol="SUPER_ADMIN", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_super):
    from app.api.deps import get_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_admin] = lambda: usuario_super
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestIncidentesCriticos:
    def test_estructura(self, client):
        r = client.get("/admin/incidentes-criticos")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("evaluado_en", "total_incidentes", "items"):
            assert key in d

    def test_glosas_muy_vencidas(self, client, db_session):
        for _ in range(3):
            db_session.add(GlosaRecord(
                eps="X", paciente="X", codigo_glosa="C",
                valor_objetado=1000, etapa="X", estado="RADICADA",
                creado_en=ahora_utc(),
                dias_restantes=-100,
            ))
        db_session.commit()

        r = client.get("/admin/incidentes-criticos")
        d = r.json()
        items = [it for it in d["items"]
                 if it["tipo"] == "GLOSAS_MUY_VENCIDAS"]
        assert len(items) == 1
        assert items[0]["count"] == 3
        assert items[0]["severidad"] == "CRITICAL"

    def test_audiencias_atrasadas(self, client, db_session):
        # Audiencia hace 5 días, sin acta
        db_session.add(ConciliacionRecord(
            glosa_id=1,
            fecha_audiencia=ahora_utc() - timedelta(days=5),
            estado_bilateral="PROGRAMADA",
            creado_en=ahora_utc(),
        ))
        db_session.commit()

        r = client.get("/admin/incidentes-criticos")
        d = r.json()
        items = [it for it in d["items"]
                 if it["tipo"] == "AUDIENCIAS_ATRASADAS"]
        assert len(items) == 1
        assert items[0]["count"] == 1

    def test_plantillas_gold_inefectivas(self, client, db_session):
        # Plantilla con 6 usos y $0 recuperado → inefectiva
        db_session.add(PlantillaGoldRecord(
            eps="X", codigo_glosa="C", tipo="ARG",
            argumento="<p>X</p>",
            usos=6, valor_recuperado=0, activa=1,
        ))
        db_session.commit()

        r = client.get("/admin/incidentes-criticos")
        d = r.json()
        items = [it for it in d["items"]
                 if it["tipo"] == "PLANTILLAS_GOLD_INEFECTIVAS"]
        assert len(items) == 1
        assert items[0]["count"] == 1

    def test_sin_incidentes(self, client):
        r = client.get("/admin/incidentes-criticos")
        d = r.json()
        assert d["total_incidentes"] == 0
        assert d["items"] == []
