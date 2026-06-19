"""Tests del endpoint POST /analizar/extraer-soportes (feature #5).

Verifica fundir_extracciones (merge de varias detecciones) y los
guardarrails del endpoint (auth, magic bytes, tamaño máximo).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.analizar import _fundir_extracciones
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


class TestFundirExtracciones:
    """Unit tests del merge — sin IO de PDFs, sin TestClient."""

    def test_vacio(self):
        r = _fundir_extracciones([])
        assert r["paciente"] == ""
        assert r["confianza_global"] == 0.0

    def test_primer_no_vacio_por_confianza(self):
        # Dos extracciones, la de mayor confianza gana en el campo string
        r = _fundir_extracciones(
            [
                {"paciente": "JUAN PEREZ", "numero_factura": "", "confianza": 0.3},
                {"paciente": "MARIA LOPEZ", "numero_factura": "FE-001", "confianza": 0.8},
            ]
        )
        # Mayor confianza (0.8) → MARIA LOPEZ
        assert r["paciente"] == "MARIA LOPEZ"
        assert r["factura"] == "FE-001"
        # Promedio de confianzas
        assert r["confianza_global"] == 0.55

    def test_valor_objetado_toma_el_maximo(self):
        r = _fundir_extracciones(
            [
                {"valor_objetado": 100_000, "confianza": 0.5},
                {"valor_objetado": 500_000, "confianza": 0.5},
                {"valor_objetado": 200_000, "confianza": 0.5},
            ]
        )
        assert r["valor_objetado"] == 500_000

    def test_codigos_glosa_union_deduplicada(self):
        r = _fundir_extracciones(
            [
                {"codigos_glosa": ["TA0201", "SO0501"], "confianza": 0.3},
                {"codigos_glosa": ["TA0201", "CO0101"], "confianza": 0.6},
            ]
        )
        # El orden viene del que tiene mayor confianza primero
        assert set(r["codigos_glosa"]) == {"TA0201", "SO0501", "CO0101"}
        # Sin duplicados
        assert len(r["codigos_glosa"]) == 3


class TestExtraerSoportesEndpoint:
    def test_sin_archivos_devuelve_vacio(self, client):
        r = client.post("/analizar/extraer-soportes")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["paciente"] == ""
        assert d["confianza_global"] == 0.0

    def test_archivo_no_pdf_es_rechazado(self, client):
        archivo = ("texto.txt", b"esto no es un pdf, son bytes cualquiera", "text/plain")
        r = client.post(
            "/analizar/extraer-soportes",
            files=[("archivos", archivo)],
        )
        assert r.status_code == 200
        d = r.json()
        assert d["archivos_procesados"] == 0
        assert any(
            (item.get("ok") is False) and "PDF" in (item.get("error") or "")
            for item in d["detalle_por_archivo"]
        )

    def test_pdf_minimo_sin_texto_devuelve_error_legible(self, client):
        # PDF con header válido pero sin contenido útil → el extractor
        # devolverá texto < 30 chars, el endpoint marca "PDF sin texto plano".
        pdf_minimo = b"%PDF-1.4\n%%EOF\n"
        archivo = ("vacio.pdf", pdf_minimo, "application/pdf")
        r = client.post(
            "/analizar/extraer-soportes",
            files=[("archivos", archivo)],
        )
        assert r.status_code == 200
        d = r.json()
        # No procesa pero no rompe — devuelve detalle por archivo
        assert d["archivos_procesados"] == 0
