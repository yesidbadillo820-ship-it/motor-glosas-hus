"""Tests de los endpoints del PDF radicable:

GET /glosas/{glosa_id}/dictamen.pdf  — PDF formal de UNA glosa
GET /glosas/lote/pdf-zip?ids=1,2,3   — ZIP con un PDF por glosa
"""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord

DICTAMEN_HTML = (
    '<table border="1"><tr><th>CÓDIGO GLOSA</th><th>VALOR OBJETADO</th>'
    "<th>CÓDIGO RESPUESTA</th></tr>"
    "<tr><td>TA0801</td><td>$36.402</td><td><b>RE9901</b></td></tr></table>"
    "<div>ARGUMENTACIÓN JURÍDICA<br/>Se objeta la glosa.</div>"
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
        eps="SANITAS",
        paciente="Paciente X",
        factura="HUS123456",
        codigo_glosa="TA0801",
        valor_objetado=36402,
        etapa="OBJECION",
        estado="RESPONDIDA",
        dictamen=DICTAMEN_HTML,
        creado_en=ahora_utc(),
    )
    base.update(kw)
    g = GlosaRecord(**base)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


class TestDictamenPdfIndividual:
    def test_glosa_inexistente_404(self, client):
        r = client.get("/glosas/99999/dictamen.pdf")
        assert r.status_code == 404
        assert "no encontrada" in r.json()["detail"].lower()

    def test_sin_dictamen_404_mensaje_claro(self, client, db_session):
        g = _seed(db_session, dictamen=None)
        r = client.get(f"/glosas/{g.id}/dictamen.pdf")
        assert r.status_code == 404
        assert "no tiene dictamen" in r.json()["detail"]

    def test_pdf_valido_con_headers(self, client, db_session):
        g = _seed(db_session)
        r = client.get(f"/glosas/{g.id}/dictamen.pdf")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert f"respuesta_glosa_HUS123456_{g.id}.pdf" in cd

    def test_pdf_contiene_codigo_glosa(self, client, db_session):
        import pdfplumber

        g = _seed(db_session)
        r = client.get(f"/glosas/{g.id}/dictamen.pdf")
        with pdfplumber.open(io.BytesIO(r.content)) as doc:
            txt = "\n".join(p.extract_text() or "" for p in doc.pages)
        assert "TA0801" in txt
        assert "RESPUESTA A GLOSA / OBJECIÓN" in txt
        assert "<table" not in txt


class TestDictamenPdfZipLote:
    def test_zip_con_un_pdf_por_glosa(self, client, db_session):
        g1 = _seed(db_session, factura="F001")
        g2 = _seed(db_session, factura="F002")
        r = client.get(f"/glosas/lote/pdf-zip?ids={g1.id},{g2.id}")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        nombres = zf.namelist()
        assert "README.txt" in nombres
        assert f"respuesta_glosa_F001_{g1.id}.pdf" in nombres
        assert f"respuesta_glosa_F002_{g2.id}.pdf" in nombres
        # Cada PDF dentro del ZIP es un PDF válido
        for n in nombres:
            if n.endswith(".pdf"):
                assert zf.read(n).startswith(b"%PDF")

    def test_glosas_sin_dictamen_omitidas_en_readme(self, client, db_session):
        g1 = _seed(db_session, factura="F003")
        g2 = _seed(db_session, factura="F004", dictamen=None)
        r = client.get(f"/glosas/lote/pdf-zip?ids={g1.id},{g2.id}")
        assert r.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert f"respuesta_glosa_F003_{g1.id}.pdf" in zf.namelist()
        assert f"respuesta_glosa_F004_{g2.id}.pdf" not in zf.namelist()
        readme = zf.read("README.txt").decode("utf-8")
        assert str(g2.id) in readme
        assert "SIN dictamen" in readme

    def test_ninguna_con_dictamen_404(self, client, db_session):
        g = _seed(db_session, dictamen=None)
        r = client.get(f"/glosas/lote/pdf-zip?ids={g.id}")
        assert r.status_code == 404

    def test_ids_invalidos_400(self, client):
        r = client.get("/glosas/lote/pdf-zip?ids=a,b")
        assert r.status_code == 400

    def test_cap_50_glosas(self, client):
        ids = ",".join(str(i) for i in range(1, 52))
        r = client.get(f"/glosas/lote/pdf-zip?ids={ids}")
        assert r.status_code == 400
        assert "50" in r.json()["detail"]

    def test_ids_inexistentes_404(self, client):
        r = client.get("/glosas/lote/pdf-zip?ids=99991,99992")
        assert r.status_code == 404
