"""Tests del endpoint GET /glosas/{id}/contexto-completo (R94 P2)."""
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


class TestContextoCompleto:
    def test_404(self, client):
        r = client.get("/glosas/99999/contexto-completo")
        assert r.status_code == 404

    def test_estructura_respuesta(self, client, db_session):
        g = _seed(db_session, eps="SANITAS", valor_objetado=5000)
        r = client.get(f"/glosas/{g.id}/contexto-completo")
        d = r.json()
        # 4 secciones top-level
        assert set(d.keys()) == {
            "glosa", "sla", "audit_resumen", "relacionadas_count",
        }
        assert d["glosa"]["id"] == g.id
        assert d["glosa"]["eps"] == "SANITAS"
        assert d["glosa"]["valor_objetado"] == 5000.0

    def test_sla_seccion(self, client, db_session):
        g = _seed(db_session,
                  fecha_vencimiento=ahora_utc() + timedelta(days=2),
                  dias_restantes=2)
        r = client.get(f"/glosas/{g.id}/contexto-completo")
        d = r.json()
        assert d["sla"]["estado_sla"] == "CRITICA"
        assert d["sla"]["color_semaforo"] == "AMARILLO"
        assert d["sla"]["cerrada"] is False

    def test_audit_resumen_seccion(self, client, db_session):
        g = _seed(db_session)
        # 3 eventos de audit
        for u in ["a@x", "b@x", "a@x"]:
            db_session.add(AuditLogRecord(
                usuario_email=u, accion="UPDATE", tabla="glosas",
                registro_id=g.id, timestamp=ahora_utc(),
            ))
        db_session.commit()

        r = client.get(f"/glosas/{g.id}/contexto-completo")
        d = r.json()
        assert d["audit_resumen"]["total_cambios"] == 3
        assert d["audit_resumen"]["usuarios_que_intervinieron"] == ["a@x", "b@x"]

    def test_relacionadas_count(self, client, db_session):
        g1 = _seed(db_session, factura="F-X", paciente="Pedro",
                   eps="E", codigo_glosa="C")
        # 2 misma factura + 1 mismo paciente (que también es misma factura)
        _seed(db_session, factura="F-X", paciente="Pedro",
              eps="E", codigo_glosa="C")
        _seed(db_session, factura="F-X", paciente="Otro",
              eps="OtraEps", codigo_glosa="C")

        r = client.get(f"/glosas/{g1.id}/contexto-completo")
        d = r.json()
        # Counts (no items)
        rc = d["relacionadas_count"]
        assert rc["misma_factura"] == 2
        assert rc["mismo_paciente"] == 1
        # mismo_codigo_y_eps: las que tienen E + C → solo 1
        assert rc["mismo_codigo_y_eps"] == 1
