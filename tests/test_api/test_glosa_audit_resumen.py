"""Tests del endpoint GET /glosas/{id}/audit-resumen (R88 P2)."""
from __future__ import annotations

from datetime import timedelta

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


def _seed_glosa(db):
    g = GlosaRecord(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    db.add(g); db.commit(); db.refresh(g)
    return g


def _seed_audit(db, glosa_id, usuario, accion, campo=None, dias_atras=0):
    db.add(AuditLogRecord(
        usuario_email=usuario, usuario_rol="AUDITOR",
        accion=accion, tabla="glosas", registro_id=glosa_id, campo=campo,
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestGlosaAuditResumen:
    def test_404_glosa_inexistente(self, client):
        r = client.get("/glosas/99999/audit-resumen")
        assert r.status_code == 404

    def test_glosa_sin_eventos(self, client, db_session):
        g = _seed_glosa(db_session)
        r = client.get(f"/glosas/{g.id}/audit-resumen")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["glosa_id"] == g.id
        assert d["total_cambios"] == 0
        assert d["primer_cambio_en"] is None
        assert d["ultimo_cambio_en"] is None
        assert d["usuarios_que_intervinieron"] == []
        assert d["eventos_por_accion"] == {}
        assert d["eventos_por_campo"] == {}

    def test_resumen_con_eventos(self, client, db_session):
        g = _seed_glosa(db_session)
        _seed_audit(db_session, g.id, "alice@x", "UPDATE", "estado", dias_atras=5)
        _seed_audit(db_session, g.id, "alice@x", "UPDATE", "estado", dias_atras=2)
        _seed_audit(db_session, g.id, "bob@x", "DECISION_EPS", "decision_eps", dias_atras=0)

        r = client.get(f"/glosas/{g.id}/audit-resumen")
        d = r.json()
        assert d["total_cambios"] == 3
        assert d["usuarios_que_intervinieron"] == ["alice@x", "bob@x"]
        assert d["eventos_por_accion"] == {"UPDATE": 2, "DECISION_EPS": 1}
        assert d["eventos_por_campo"] == {"estado": 2, "decision_eps": 1}
        assert d["primer_cambio_en"] is not None
        assert d["ultimo_cambio_en"] is not None
        # Primer cambio < último cambio
        assert d["primer_cambio_en"] < d["ultimo_cambio_en"]

    def test_excluye_eventos_de_otra_glosa(self, client, db_session):
        g1 = _seed_glosa(db_session)
        g2 = _seed_glosa(db_session)
        _seed_audit(db_session, g1.id, "u@x", "UPDATE", "estado")
        _seed_audit(db_session, g2.id, "u@x", "UPDATE", "estado")
        _seed_audit(db_session, g2.id, "u@x", "UPDATE", "etapa")

        r = client.get(f"/glosas/{g1.id}/audit-resumen")
        d = r.json()
        assert d["total_cambios"] == 1

    def test_excluye_eventos_de_otra_tabla(self, client, db_session):
        g = _seed_glosa(db_session)
        # Evento sobre otra tabla — no debe contarse
        db_session.add(AuditLogRecord(
            usuario_email="u@x", accion="X", tabla="usuarios",
            registro_id=g.id, timestamp=ahora_utc(),
        ))
        db_session.commit()

        r = client.get(f"/glosas/{g.id}/audit-resumen")
        d = r.json()
        assert d["total_cambios"] == 0
