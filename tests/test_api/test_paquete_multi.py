"""Tests del endpoint GET /glosas/exportar-paquete-multi.zip (R138 P2)."""
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


def _seed(db, gid, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(id=gid, **base))
    db.commit()


class TestPaqueteMulti:
    def test_ids_invalidos_400(self, client):
        r = client.get("/glosas/exportar-paquete-multi.zip?ids=abc")
        assert r.status_code == 400

    def test_sin_glosas_404(self, client):
        r = client.get("/glosas/exportar-paquete-multi.zip?ids=999,888")
        assert r.status_code == 404

    def test_genera_zip_con_subcarpetas(self, client, db_session):
        _seed(db_session, gid=1, eps="SANITAS")
        _seed(db_session, gid=2, eps="NUEVA EPS",
              dictamen="texto largo de dictamen para glosa 2")

        r = client.get("/glosas/exportar-paquete-multi.zip?ids=1,2")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        nombres = zf.namelist()
        assert "README.txt" in nombres
        assert "glosa-1/glosa.json" in nombres
        assert "glosa-2/glosa.json" in nombres
        # Solo glosa-2 tiene dictamen
        assert "glosa-2/dictamen.txt" in nombres
        assert "glosa-1/dictamen.txt" not in nombres

    def test_glosa_json_correcto(self, client, db_session):
        _seed(db_session, gid=5, eps="EPS_X", valor_objetado=12345)
        r = client.get("/glosas/exportar-paquete-multi.zip?ids=5")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        with zf.open("glosa-5/glosa.json") as f:
            d = json.load(f)
        assert d["id"] == 5
        assert d["eps"] == "EPS_X"
        assert d["valor_objetado"] == 12345.0

    def test_readme_lista_no_encontrados(self, client, db_session):
        _seed(db_session, gid=1)
        r = client.get("/glosas/exportar-paquete-multi.zip?ids=1,999")
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        with zf.open("README.txt") as f:
            readme = f.read().decode("utf-8")
        assert "999" in readme
        assert "no encontrados" in readme.lower()

    def test_max_100(self, client):
        ids_str = ",".join(str(i) for i in range(1, 102))  # 101 IDs
        r = client.get(f"/glosas/exportar-paquete-multi.zip?ids={ids_str}")
        assert r.status_code == 400
