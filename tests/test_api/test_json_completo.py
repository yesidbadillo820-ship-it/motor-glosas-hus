"""Tests del endpoint GET /glosas/{id}/json-completo (R142 P2)."""
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


class TestJsonCompleto:
    def test_404(self, client):
        r = client.get("/glosas/99999/json-completo")
        assert r.status_code == 404

    def test_devuelve_todas_las_columnas(self, client, db_session):
        g = _seed(db_session, eps="SANITAS", paciente="Pedro",
                  factura="F-1", valor_objetado=12345)
        r = client.get(f"/glosas/{g.id}/json-completo")
        d = r.json()
        # Algunas columnas obligatorias
        assert d["id"] == g.id
        assert d["eps"] == "SANITAS"
        assert d["paciente"] == "Pedro"
        assert d["factura"] == "F-1"
        assert d["valor_objetado"] == 12345.0

    def test_datetime_es_iso(self, client, db_session):
        g = _seed(db_session)
        r = client.get(f"/glosas/{g.id}/json-completo")
        d = r.json()
        assert "T" in d["creado_en"]  # ISO format

    def test_incluye_columnas_diversas(self, client, db_session):
        g = _seed(db_session)
        r = client.get(f"/glosas/{g.id}/json-completo")
        d = r.json()
        # Las 50+ columnas del modelo están presentes
        for col in ("id", "creado_en", "eps", "paciente", "factura",
                    "codigo_glosa", "valor_objetado", "etapa",
                    "estado", "dictamen", "dias_restantes"):
            assert col in d
