"""Tests del endpoint GET /sistema/cumplimiento-resolucion (R134 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import UsuarioRecord


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
def usuario_coord():
    return UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestCumplimientoResolucion:
    def test_estructura(self, client):
        r = client.get("/sistema/cumplimiento-resolucion")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("regulacion", "total_items", "items_cumplidos",
                    "tasa_cumplimiento_pct", "items"):
            assert key in d

    def test_cada_item_tiene_metadata(self, client):
        r = client.get("/sistema/cumplimiento-resolucion")
        d = r.json()
        for it in d["items"]:
            assert "articulo" in it
            assert "requisito" in it
            assert "cumple" in it
            assert "evidencia" in it
            assert isinstance(it["cumple"], bool)

    def test_lista_articulos_clave(self, client):
        r = client.get("/sistema/cumplimiento-resolucion")
        d = r.json()
        articulos = [it["articulo"] for it in d["items"]]
        # Algunos artículos clave deben estar
        assert any("Art. 6" in a for a in articulos)
        assert any("Art. 18" in a for a in articulos)
        assert any("Habeas Data" in a for a in articulos)

    def test_tasa_cumplimiento_consistente(self, client):
        r = client.get("/sistema/cumplimiento-resolucion")
        d = r.json()
        cumple = sum(1 for it in d["items"] if it["cumple"])
        assert d["items_cumplidos"] == cumple
        esperada = round(100 * cumple / d["total_items"], 2)
        assert d["tasa_cumplimiento_pct"] == esperada
