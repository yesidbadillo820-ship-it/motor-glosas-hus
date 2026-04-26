"""Tests del endpoint GET /glosas/{id}/relacionadas (R93 P2)."""
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
        factura="F-001", valor_objetado=1000, etapa="X",
        estado="RADICADA", creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


class TestGlosasRelacionadas:
    def test_404(self, client):
        r = client.get("/glosas/99999/relacionadas")
        assert r.status_code == 404

    def test_misma_factura(self, client, db_session):
        g1 = _seed(db_session, factura="F-100")
        _seed(db_session, factura="F-100")  # misma factura
        _seed(db_session, factura="F-100")  # misma factura
        _seed(db_session, factura="F-200")  # otra
        r = client.get(f"/glosas/{g1.id}/relacionadas")
        d = r.json()
        # 2 con misma factura (excluye la propia)
        assert len(d["misma_factura"]) == 2
        assert all(g["factura"] == "F-100" for g in d["misma_factura"])

    def test_mismo_paciente(self, client, db_session):
        g1 = _seed(db_session, paciente="Pedro Pérez")
        _seed(db_session, paciente="Pedro Pérez")
        _seed(db_session, paciente="María García")
        r = client.get(f"/glosas/{g1.id}/relacionadas")
        d = r.json()
        assert len(d["mismo_paciente"]) == 1
        assert d["mismo_paciente"][0]["id"] != g1.id

    def test_mismo_codigo_y_eps(self, client, db_session):
        g1 = _seed(db_session, eps="SANITAS", codigo_glosa="TA0201")
        _seed(db_session, eps="SANITAS", codigo_glosa="TA0201")  # match
        _seed(db_session, eps="SANITAS", codigo_glosa="FA0603")  # no
        _seed(db_session, eps="NUEVA EPS", codigo_glosa="TA0201")  # no
        r = client.get(f"/glosas/{g1.id}/relacionadas")
        d = r.json()
        assert len(d["mismo_codigo_y_eps"]) == 1

    def test_excluye_la_misma_glosa(self, client, db_session):
        g1 = _seed(db_session, factura="F-X", paciente="P-X",
                   eps="E", codigo_glosa="C")
        r = client.get(f"/glosas/{g1.id}/relacionadas")
        d = r.json()
        # La propia glosa nunca debe aparecer en sus relacionadas
        for grupo in [d["misma_factura"], d["mismo_paciente"],
                      d["mismo_codigo_y_eps"]]:
            assert all(g["id"] != g1.id for g in grupo)

    def test_factura_NA_no_busca(self, client, db_session):
        # Glosa con factura "N/A" — no deben aparecer relacionadas por factura
        g1 = _seed(db_session, factura="N/A")
        _seed(db_session, factura="N/A")
        r = client.get(f"/glosas/{g1.id}/relacionadas")
        d = r.json()
        assert d["misma_factura"] == []

    def test_limite_por_grupo(self, client, db_session):
        g1 = _seed(db_session, factura="F-MEGA")
        for _ in range(15):
            _seed(db_session, factura="F-MEGA")
        r = client.get(f"/glosas/{g1.id}/relacionadas")
        d = r.json()
        assert d["limite_por_grupo"] == 10
        assert len(d["misma_factura"]) == 10
