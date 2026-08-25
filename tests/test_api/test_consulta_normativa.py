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


class TestLasCircularesQueEntregoElAuditor:
    """24-08-2026: Yesid entregó los PDF reales de la Circular 047/2025
    (UVB, Manual SOAT 2026) y la Circular 19/2024 CNPMDM (precio máximo de
    medicamentos) para que la biblioteca conteste cuando las busquen."""

    def test_buscar_uvb_encuentra_la_047_con_sustancia(self):
        from app.api.routers.consulta_normativa import _buscar_normas

        r = _buscar_normas("valor UVB manual tarifario SOAT 2026")
        assert r, "la búsqueda no devolvió nada"
        top = r[0]
        assert "047" in top["norma"]
        assert "12.110" in top["texto"], "no cita el valor de la UVB 2026"

    def test_buscar_precio_maximo_de_medicamentos_encuentra_la_19(self):
        from app.api.routers.consulta_normativa import _buscar_normas

        r = _buscar_normas("precio máximo de venta medicamentos control directo")
        assert any("Circular 19 de 2024" in n["norma"] for n in r), (
            "la Circular 19/2024 CNPMDM no aparece: es la defensa de las "
            "glosas de medicamentos regulados"
        )

    def test_la_19_cita_el_margen_de_la_ips(self):
        """El arma concreta: Parágrafo 2 del Art. 1 — la IPS puede adicionar
        el margen del Art. 11 de la Circular 18 de 2024. Sin eso en el texto,
        la biblioteca da el nombre pero no la defensa."""
        from app.api.routers.consulta_normativa import CATALOGO_NORMAS

        entrada = next(n for n in CATALOGO_NORMAS if n["clave"] == "CIRCULAR 19 DE 2024 CNPMDM")
        kws = " ".join(entrada["keywords"])
        assert "margen" in kws and "Circular 18 de 2024" in kws
        assert "deroga la Circular 13 de 2022" in entrada["titulo"]
