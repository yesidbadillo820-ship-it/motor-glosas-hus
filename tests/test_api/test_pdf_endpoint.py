"""Tests del endpoint POST /pdf/ocr (R83 P2)."""
from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import UsuarioRecord


def _pdf_minimal(texto: str = "test") -> bytes:
    """Genera PDF mínimo con reportlab si está disponible."""
    try:
        from reportlab.pdfgen import canvas
    except ImportError:
        pytest.skip("reportlab no instalado")
    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 800, texto)
    c.save()
    return buf.getvalue()


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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestPdfOcr:
    def test_archivo_no_pdf_400(self, client):
        r = client.post("/pdf/ocr", files={
            "archivo": ("test.txt", b"contenido texto", "text/plain"),
        })
        assert r.status_code == 400

    def test_pdf_muy_grande_400(self, client):
        # PDF de 31 MB (excede límite 30MB)
        big = b"%PDF-1.7\n" + b"x" * (31_000_000)
        r = client.post("/pdf/ocr", files={
            "archivo": ("big.pdf", big, "application/pdf"),
        })
        assert r.status_code == 400

    def test_pdf_valido_devuelve_texto(self, client):
        pdf = _pdf_minimal("Texto del PDF de prueba")
        r = client.post("/pdf/ocr", files={
            "archivo": ("test.pdf", pdf, "application/pdf"),
        })
        assert r.status_code == 200
        d = r.json()
        assert "texto" in d
        assert "metodo" in d
        assert "caracteres" in d
        assert d["caracteres"] > 0
        # El texto debe contener "Texto del PDF de prueba"
        assert "Texto del PDF" in d["texto"]
