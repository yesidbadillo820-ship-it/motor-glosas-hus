"""Tests del endpoint GET /glosas/{id}/exportar-evidencia.zip (R108 P1)."""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AuditLogRecord, GlosaRecord, UsuarioRecord


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


class TestEvidenciaZip:
    def test_404(self, client):
        r = client.get("/glosas/99999/exportar-evidencia.zip")
        assert r.status_code == 404

    def test_genera_zip_valido(self, client, db_session):
        g = _seed(db_session, eps="SANITAS", dictamen="texto del dictamen")
        r = client.get(f"/glosas/{g.id}/exportar-evidencia.zip")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        # Es un ZIP válido
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        nombres = zf.namelist()
        assert "README.txt" in nombres
        assert "glosa.json" in nombres
        assert "audit_log.json" in nombres
        assert "dictamen.txt" in nombres

    def test_glosa_json_correcto(self, client, db_session):
        g = _seed(db_session, eps="NUEVA EPS", paciente="Pedro",
                  valor_objetado=12345)
        r = client.get(f"/glosas/{g.id}/exportar-evidencia.zip")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        with zf.open("glosa.json") as f:
            d = json.load(f)
        assert d["eps"] == "NUEVA EPS"
        assert d["paciente"] == "Pedro"
        assert d["valor_objetado"] == 12345.0

    def test_sin_dictamen_no_archivo(self, client, db_session):
        g = _seed(db_session, dictamen=None)
        r = client.get(f"/glosas/{g.id}/exportar-evidencia.zip")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        # Si no hay dictamen, no se incluye dictamen.txt
        assert "dictamen.txt" not in zf.namelist()

    def test_audit_log_incluido(self, client, db_session):
        g = _seed(db_session)
        db_session.add(AuditLogRecord(
            usuario_email="a@x", accion="UPDATE", tabla="glosas",
            registro_id=g.id, timestamp=ahora_utc(),
        ))
        db_session.commit()

        r = client.get(f"/glosas/{g.id}/exportar-evidencia.zip")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        with zf.open("audit_log.json") as f:
            audit = json.load(f)
        assert len(audit) == 1
        assert audit[0]["accion"] == "UPDATE"

    def test_content_disposition_attachment(self, client, db_session):
        g = _seed(db_session)
        r = client.get(f"/glosas/{g.id}/exportar-evidencia.zip")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".zip" in cd
