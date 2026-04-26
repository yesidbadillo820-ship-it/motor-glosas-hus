"""Tests del endpoint GET /usuarios/yo/comentarios-emitidos (R291 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ComentarioGlosaRecord,
    GlosaRecord,
    UsuarioRecord,
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
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice", rol="AUDITOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_glosa(db, glosa_id):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_com(db, glosa_id, autor, mencion=None, resuelto=0,
              resuelto_por=None):
    db.add(ComentarioGlosaRecord(
        glosa_id=glosa_id, autor_email=autor, texto="t",
        mencion=mencion, resuelto=resuelto,
        resuelto_por=resuelto_por,
        resuelto_en=ahora_utc() if resuelto_por else None,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestYoComentariosEmitidos:
    def test_metricas(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        _seed_com(
            db_session, 1, "alice@hus.com", mencion="bob@x",
        )
        _seed_com(db_session, 2, "alice@hus.com", resuelto=1)
        _seed_com(db_session, 1, "bob@hus.com")  # otro autor

        # Bob resuelve un comentario de Alice
        _seed_com(
            db_session, 2, "carl@x", resuelto=1,
            resuelto_por="alice@hus.com",
        )

        r = client.get("/usuarios/yo/comentarios-emitidos")
        d = r.json()
        assert d["total_emitidos"] == 2
        assert d["menciones_hechas"] == 1
        assert d["resueltos"] == 1
        assert d["resueltos_por_mi"] == 1
        assert d["glosas_distintas"] == 2

    def test_solo_propios(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_com(db_session, 1, "bob@hus.com")
        r = client.get("/usuarios/yo/comentarios-emitidos")
        d = r.json()
        assert d["total_emitidos"] == 0
