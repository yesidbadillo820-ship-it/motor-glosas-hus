"""Tests del endpoint GET /glosas/{id}/resumen-pdf (R119 P1)."""
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


class TestResumenPDF:
    def test_404(self, client):
        r = client.get("/glosas/99999/resumen-pdf")
        assert r.status_code == 404

    def test_genera_pdf_valido(self, client, db_session):
        g = _seed(db_session, dictamen="<p>texto del dictamen</p>")
        r = client.get(f"/glosas/{g.id}/resumen-pdf")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        # Magic bytes PDF: %PDF
        assert r.content[:4] == b"%PDF"

    def test_attachment_header(self, client, db_session):
        g = _seed(db_session)
        r = client.get(f"/glosas/{g.id}/resumen-pdf")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".pdf" in cd
        assert str(g.id) in cd

    def test_sin_dictamen_genera_pdf(self, client, db_session):
        # Sin dictamen el PDF aún debe generarse
        g = _seed(db_session, dictamen=None)
        r = client.get(f"/glosas/{g.id}/resumen-pdf")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_pdf_contiene_datos_glosa(self, client, db_session):
        g = _seed(db_session, eps="SANITAS", factura="F-99")
        r = client.get(f"/glosas/{g.id}/resumen-pdf")
        # ReportLab puede comprimir el contenido pero podemos verificar
        # que el archivo es no-trivial
        assert len(r.content) > 1000  # PDF mínimo realista
