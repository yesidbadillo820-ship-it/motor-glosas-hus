"""Tests del endpoint /glosas/{id}/dictamen.md (R69 P2)."""
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


def _seed_glosa(db, dictamen):
    g = GlosaRecord(
        eps="FAMISANAR", paciente="X", codigo_glosa="TA0201",
        valor_objetado=168_563, etapa="X", estado="RADICADA",
        factura="FE-001",
        modelo_ia="anthropic/claude-sonnet-4-6",
        dictamen=dictamen,
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


class TestDictamenMarkdown:
    def test_glosa_inexistente_404(self, client):
        r = client.get("/glosas/99999/dictamen.md")
        assert r.status_code == 404

    def test_sin_dictamen_400(self, client, db_session):
        g = _seed_glosa(db_session, dictamen=None)
        r = client.get(f"/glosas/{g.id}/dictamen.md")
        assert r.status_code == 400

    def test_descarga_con_content_disposition(self, client, db_session):
        g = _seed_glosa(db_session, dictamen="<p>contenido</p>")
        r = client.get(f"/glosas/{g.id}/dictamen.md")
        assert r.status_code == 200
        assert "attachment" in r.headers.get("content-disposition", "")
        assert ".md" in r.headers.get("content-disposition", "")
        assert r.headers["content-type"].startswith("text/markdown")

    def test_cabecera_metadata_incluida(self, client, db_session):
        g = _seed_glosa(db_session, dictamen="<p>x</p>")
        r = client.get(f"/glosas/{g.id}/dictamen.md")
        body = r.text
        assert "FAMISANAR" in body
        assert "TA0201" in body
        assert "168,563" in body
        assert "FE-001" in body

    def test_html_se_convierte_a_md(self, client, db_session):
        html = (
            "<h3>Sección 1</h3>"
            "<p>Texto con <b>negrita</b> y <i>cursiva</i></p>"
            "<ul><li>punto uno</li><li>punto dos</li></ul>"
        )
        g = _seed_glosa(db_session, dictamen=html)
        r = client.get(f"/glosas/{g.id}/dictamen.md")
        body = r.text
        # Encabezado h3 → ###
        assert "### Sección 1" in body
        # Negrita → **...**
        assert "**negrita**" in body
        # Cursiva → *...*
        assert "*cursiva*" in body
        # Lista → -
        assert "- punto uno" in body
        assert "- punto dos" in body

    def test_no_quedan_tags_html(self, client, db_session):
        html = '<div style="color:red">contenido <span>span</span></div>'
        g = _seed_glosa(db_session, dictamen=html)
        r = client.get(f"/glosas/{g.id}/dictamen.md")
        body = r.text
        # Sin tags
        assert "<div" not in body
        assert "</div>" not in body
        assert "<span>" not in body

    def test_entidades_html_decoded(self, client, db_session):
        html = "<p>copia &amp; pega · &lt;ejemplo&gt;</p>"
        g = _seed_glosa(db_session, dictamen=html)
        r = client.get(f"/glosas/{g.id}/dictamen.md")
        body = r.text
        assert "&amp;" not in body
        assert "&lt;" not in body
        assert "& pega" in body
        assert "<ejemplo>" in body
