"""Tests del endpoint GET /admin/consecutivos-duplicados (R287 P1)."""
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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, glosa_id, consecutivo):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        consecutivo_dgh=consecutivo,
    ))
    db.commit()


class TestConsecutivosDuplicados:
    def test_detecta_duplicados(self, client, db_session):
        _seed(db_session, 1, "DGH001")
        _seed(db_session, 2, "DGH001")  # duplicado
        _seed(db_session, 3, "DGH002")  # único

        r = client.get("/admin/consecutivos-duplicados")
        d = r.json()
        assert d["total_duplicados"] == 1
        assert d["items"][0]["consecutivo_dgh"] == "DGH001"
        assert sorted(d["items"][0]["glosa_ids"]) == [1, 2]

    def test_sin_duplicados(self, client, db_session):
        _seed(db_session, 1, "DGH001")
        _seed(db_session, 2, "DGH002")
        r = client.get("/admin/consecutivos-duplicados")
        d = r.json()
        assert d["total_duplicados"] == 0
