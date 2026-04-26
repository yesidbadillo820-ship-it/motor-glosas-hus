"""Tests del endpoint GET /glosas/{id}/duplicados-potenciales (R99 P2)."""
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
        eps="SANITAS", paciente="X", codigo_glosa="TA0201",
        factura="F-001", valor_objetado=10000, etapa="X",
        estado="RADICADA", creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


class TestDuplicadosPotenciales:
    def test_404(self, client):
        r = client.get("/glosas/99999/duplicados-potenciales")
        assert r.status_code == 404

    def test_factura_NA_no_evaluable(self, client, db_session):
        g = _seed(db_session, factura="N/A")
        r = client.get(f"/glosas/{g.id}/duplicados-potenciales")
        d = r.json()
        assert d["candidatos"] == []
        assert "razon_no_evaluable" in d

    def test_detecta_duplicado_exacto(self, client, db_session):
        g1 = _seed(db_session, eps="SANITAS", factura="F-X",
                   codigo_glosa="TA0201", valor_objetado=10000)
        # Duplicado exacto
        _seed(db_session, eps="SANITAS", factura="F-X",
              codigo_glosa="TA0201", valor_objetado=10000)

        r = client.get(f"/glosas/{g1.id}/duplicados-potenciales")
        d = r.json()
        assert d["total_candidatos"] == 1
        assert d["candidatos"][0]["score_similitud"] == 100.0

    def test_no_detecta_si_eps_distinta(self, client, db_session):
        g1 = _seed(db_session, eps="SANITAS", factura="F-X")
        _seed(db_session, eps="NUEVA EPS", factura="F-X")
        r = client.get(f"/glosas/{g1.id}/duplicados-potenciales")
        assert r.json()["total_candidatos"] == 0

    def test_no_detecta_si_factura_distinta(self, client, db_session):
        g1 = _seed(db_session, factura="F-X")
        _seed(db_session, factura="F-Y")
        r = client.get(f"/glosas/{g1.id}/duplicados-potenciales")
        assert r.json()["total_candidatos"] == 0

    def test_no_detecta_si_codigo_distinto(self, client, db_session):
        g1 = _seed(db_session, codigo_glosa="TA0201")
        _seed(db_session, codigo_glosa="FA0603")
        r = client.get(f"/glosas/{g1.id}/duplicados-potenciales")
        assert r.json()["total_candidatos"] == 0

    def test_score_decrece_con_diff_valor(self, client, db_session):
        g1 = _seed(db_session, valor_objetado=10000)
        # Diff 10% → score 90
        _seed(db_session, valor_objetado=11000)
        r = client.get(f"/glosas/{g1.id}/duplicados-potenciales")
        d = r.json()
        assert d["candidatos"][0]["score_similitud"] < 100
        assert d["candidatos"][0]["score_similitud"] >= 80

    def test_excluye_la_propia_glosa(self, client, db_session):
        g1 = _seed(db_session)
        r = client.get(f"/glosas/{g1.id}/duplicados-potenciales")
        d = r.json()
        # No debe aparecerse a sí misma
        ids = [c["id"] for c in d["candidatos"]]
        assert g1.id not in ids
