"""Tests del CRUD /glosas/{id}/comentarios (R77 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import ComentarioGlosaRecord, GlosaRecord, UsuarioRecord


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
    return UsuarioRecord(
        id=1, email="auditor@hus.com", nombre="Juan",
        rol="AUDITOR", activo=1,
    )


@pytest.fixture
def glosa(db_session):
    g = GlosaRecord(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
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


class TestComentarios:
    def test_listar_vacio(self, client, glosa):
        r = client.get(f"/glosas/{glosa.id}/comentarios/")
        assert r.status_code == 200
        # Lista vacía
        d = r.json()
        assert isinstance(d, list)
        assert d == []

    def test_agregar_y_listar(self, client, glosa, db_session):
        r = client.post(f"/glosas/{glosa.id}/comentarios/", json={
            "texto": "El argumento debe citar Art. 57",
        })
        assert r.status_code == 201, r.text
        d = r.json()
        assert "id" in d
        # Verificar en BD
        c = db_session.query(ComentarioGlosaRecord).filter_by(glosa_id=glosa.id).first()
        assert c is not None
        assert "Art. 57" in c.texto

    def test_agregar_a_glosa_inexistente_404(self, client):
        r = client.post("/glosas/99999/comentarios/", json={
            "texto": "no debería funcionar",
        })
        assert r.status_code == 404

    def test_detecta_mencion_en_texto(self, client, glosa, db_session):
        """Si el texto trae @email@dominio, lo guarda como mencion."""
        r = client.post(f"/glosas/{glosa.id}/comentarios/", json={
            "texto": "Hola @coordinador@hus.com revisa esto",
        })
        d = r.json()
        assert d["mencion"] == "coordinador@hus.com"

    def test_resolver_comentario(self, client, glosa, db_session):
        r = client.post(f"/glosas/{glosa.id}/comentarios/", json={
            "texto": "Revisar argumento por favor",
        })
        cid = r.json()["id"]
        r2 = client.patch(f"/glosas/{glosa.id}/comentarios/{cid}/resolver")
        assert r2.status_code == 200
        # Verificar en BD: resuelto_en se llenó
        c = db_session.query(ComentarioGlosaRecord).filter_by(id=cid).first()
        assert c.resuelto_en is not None
        assert c.resuelto == 1
