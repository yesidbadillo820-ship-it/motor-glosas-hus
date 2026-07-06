"""Tests de los endpoints de consulta normativa.

La UI (panel Consulta Normativa) ya llamaba a estos endpoints, pero el
backend solo tenía /normas/export.json → el panel daba 404 ("de lujo, no
genera nada funcional" — feedback Yesid). Estos tests fijan el contrato:

  POST /consulta-normativa          → buscar en la biblioteca
  GET  /consulta-normativa/normas   → índice de normas
"""

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
def client(db_session):
    from app.api.deps import get_usuario_actual
    from app.main import app

    u = UsuarioRecord(id=1, email="auditor@hus.com", nombre="A", rol="AUDITOR", activo=1)
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: u
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestBuscarBiblioteca:
    def test_busqueda_historia_clinica(self, client):
        r = client.post("/consulta-normativa", json={"pregunta": "historia clinica", "limite": 5})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_encontrados"] >= 1
        # La Res. 1995/1999 (HC) debe estar entre los resultados
        nombres = " ".join(x["norma"] for x in d["resultados"])
        assert "1995" in nombres

    def test_cada_resultado_tiene_contrato(self, client):
        r = client.post("/consulta-normativa", json={"pregunta": "glosa tarifas plazo"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["resultados"], "esperaba al menos un resultado"
        res = d["resultados"][0]
        for campo in ("norma", "articulo", "titulo", "texto", "score"):
            assert campo in res

    def test_pregunta_vacia_devuelve_vacio(self, client):
        r = client.post("/consulta-normativa", json={"pregunta": "   "})
        assert r.status_code == 200
        assert r.json()["total_encontrados"] == 0

    def test_pregunta_sin_match_devuelve_vacio(self, client):
        r = client.post("/consulta-normativa", json={"pregunta": "xyzzy zxcvb qwerty"})
        assert r.status_code == 200
        assert r.json()["total_encontrados"] == 0

    def test_limite_respetado(self, client):
        r = client.post("/consulta-normativa", json={"pregunta": "salud", "limite": 3})
        assert r.status_code == 200
        assert len(r.json()["resultados"]) <= 3


class TestListarNormas:
    def test_lista_no_vacia(self, client):
        r = client.get("/consulta-normativa/normas")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] >= 100  # >100 normas en el catálogo HUS
        assert len(d["normas"]) == d["total"]

    def test_cada_norma_tiene_campos(self, client):
        r = client.get("/consulta-normativa/normas")
        n = r.json()["normas"][0]
        assert "nombre" in n
        assert "titulo" in n
        assert "num_articulos" in n

    def test_orden_alfabetico(self, client):
        r = client.get("/consulta-normativa/normas")
        nombres = [n["nombre"] for n in r.json()["normas"]]
        assert nombres == sorted(nombres)
