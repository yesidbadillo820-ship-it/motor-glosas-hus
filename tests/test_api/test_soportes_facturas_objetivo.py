"""Tests del endpoint /soportes-auto/facturas-objetivo (jump-box agent)."""
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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1, nombre="ADMIN",
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual, get_auditor_o_superior
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    app.dependency_overrides[get_auditor_o_superior] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_glosa(db, factura: str, estado: str = "RADICADA",
                workflow_state: str = None) -> None:
    g = GlosaRecord(
        eps="X",
        paciente="X",
        factura=factura,
        etapa="INICIAL",
        estado=estado,
        workflow_state=workflow_state,
        creado_en=ahora_utc(),
    )
    db.add(g)
    db.commit()


class TestFacturasObjetivo:
    def test_devuelve_solo_pendientes(self, client, db_session):
        # Pendientes (deben aparecer)
        _seed_glosa(db_session, "HUS001", "RADICADA")
        _seed_glosa(db_session, "HUS002", "REQUIERE_SOPORTES")
        # Cerradas (deben filtrarse)
        _seed_glosa(db_session, "HUS003", "LEVANTADA")
        _seed_glosa(db_session, "HUS004", "RATIFICADA")
        _seed_glosa(db_session, "HUS005", "ACEPTADA")
        _seed_glosa(db_session, "HUS006", "RADICADA", workflow_state="RESPONDIDA")
        _seed_glosa(db_session, "HUS007", "DUPLICADA_OCULTA")

        r = client.get("/soportes-auto/facturas-objetivo")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 2
        assert sorted(d["facturas"]) == ["HUS001", "HUS002"]

    def test_lista_vacia_cuando_no_hay_glosas(self, client):
        r = client.get("/soportes-auto/facturas-objetivo")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 0
        assert d["facturas"] == []

    def test_facturas_unicas_aunque_haya_duplicados(self, client, db_session):
        # Dos glosas con la misma factura (TA + SO por ejemplo)
        _seed_glosa(db_session, "HUS001", "RADICADA")
        _seed_glosa(db_session, "HUS001", "RADICADA")
        r = client.get("/soportes-auto/facturas-objetivo")
        d = r.json()
        # Distinct → solo 1
        assert d["total"] == 1
        assert d["facturas"] == ["HUS001"]
