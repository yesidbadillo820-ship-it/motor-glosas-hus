"""Tests del endpoint /glosas/{id}/dictamen.txt (R81 P1)."""
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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


def _seed(db, dictamen):
    g = GlosaRecord(
        eps="FAMISANAR", paciente="X", codigo_glosa="TA0201",
        valor_objetado=168_563, etapa="X", estado="RADICADA",
        factura="FE-001", dictamen=dictamen,
        creado_en=ahora_utc(),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestDictamenTxt:
    def test_404_glosa_inexistente(self, client):
        r = client.get("/glosas/99999/dictamen.txt")
        assert r.status_code == 404

    def test_400_sin_dictamen(self, client, db_session):
        g = _seed(db_session, dictamen=None)
        r = client.get(f"/glosas/{g.id}/dictamen.txt")
        assert r.status_code == 400

    def test_descarga_attachment_txt(self, client, db_session):
        g = _seed(db_session, dictamen="<p>contenido</p>")
        r = client.get(f"/glosas/{g.id}/dictamen.txt")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert ".txt" in r.headers.get("content-disposition", "")

    def test_cabecera_con_metadata(self, client, db_session):
        g = _seed(db_session, dictamen="<p>x</p>")
        r = client.get(f"/glosas/{g.id}/dictamen.txt")
        body = r.text
        assert f"DICTAMEN GLOSA #{g.id}" in body
        assert "FAMISANAR" in body
        assert "TA0201" in body
        assert "168,563" in body
        assert "FE-001" in body

    def test_strip_total_de_html(self, client, db_session):
        html = '<div style="color:red"><p>Texto con <b>negrita</b></p></div>'
        g = _seed(db_session, dictamen=html)
        r = client.get(f"/glosas/{g.id}/dictamen.txt")
        body = r.text
        # Sin tags
        assert "<div" not in body
        assert "<p>" not in body
        assert "<b>" not in body
        # Pero el texto sí está
        assert "negrita" in body

    def test_entidades_decoded(self, client, db_session):
        g = _seed(db_session, dictamen="<p>copia &amp; pega · &quot;ejemplo&quot;</p>")
        r = client.get(f"/glosas/{g.id}/dictamen.txt")
        body = r.text
        assert "&amp;" not in body
        assert "& pega" in body
        assert '"ejemplo"' in body
