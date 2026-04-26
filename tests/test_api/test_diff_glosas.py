"""Tests del endpoint GET /glosas/{id}/diff/{otra_id} (R93 P1)."""
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
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


class TestDiffGlosas:
    def test_404_primera(self, client, db_session):
        g = _seed(db_session)
        r = client.get(f"/glosas/99999/diff/{g.id}")
        assert r.status_code == 404

    def test_404_segunda(self, client, db_session):
        g = _seed(db_session)
        r = client.get(f"/glosas/{g.id}/diff/99999")
        assert r.status_code == 404

    def test_glosas_identicas_sin_diferencias(self, client, db_session):
        g1 = _seed(db_session, eps="SANITAS", paciente="A", valor_objetado=100)
        g2 = _seed(db_session, eps="SANITAS", paciente="A", valor_objetado=100)
        r = client.get(f"/glosas/{g1.id}/diff/{g2.id}")
        d = r.json()
        assert d["campos_diferentes"] == []
        assert d["total_diferencias"] == 0

    def test_destaca_campos_diferentes(self, client, db_session):
        g1 = _seed(db_session, eps="SANITAS", paciente="Pedro",
                   estado="LEVANTADA", valor_objetado=5000)
        g2 = _seed(db_session, eps="SANITAS", paciente="Juan",
                   estado="RATIFICADA", valor_objetado=5000)
        r = client.get(f"/glosas/{g1.id}/diff/{g2.id}")
        d = r.json()
        # paciente y estado son distintos; eps y valor son iguales
        assert "paciente" in d["campos_diferentes"]
        assert "estado" in d["campos_diferentes"]
        assert "eps" not in d["campos_diferentes"]
        assert "valor_objetado" not in d["campos_diferentes"]
        assert d["total_diferencias"] == 2

    def test_estructura_respuesta(self, client, db_session):
        g1 = _seed(db_session, eps="A")
        g2 = _seed(db_session, eps="B")
        r = client.get(f"/glosas/{g1.id}/diff/{g2.id}")
        d = r.json()
        assert d["glosa_a"]["id"] == g1.id
        assert d["glosa_a"]["eps"] == "A"
        assert d["glosa_b"]["id"] == g2.id
        assert d["glosa_b"]["eps"] == "B"
