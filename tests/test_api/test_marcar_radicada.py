"""Tests de POST /glosas/{id}/marcar-radicada — registro de radicación
ante la entidad con evidencia auditable (numero_radicado + fecha +
quién + observación + entrada MARCAR_RADICADA en el audit log)."""

from __future__ import annotations

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


def _client_con(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    return TestClient(app)


@pytest.fixture
def coordinador():
    return UsuarioRecord(id=1, email="coord@hus.com", rol="COORDINADOR", activo=1)


@pytest.fixture
def client(db_session, coordinador):
    from app.main import app

    with _client_con(db_session, coordinador) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, **kw):
    base = dict(
        eps="SANITAS",
        factura="HUS123",
        codigo_glosa="TA0801",
        valor_objetado=1000,
        etapa="OBJECION",
        estado="RESPONDIDA",
        workflow_state="APROBADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    g = GlosaRecord(**base)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


class TestMarcarRadicada:
    def test_glosa_inexistente_404(self, client):
        r = client.post("/glosas/99999/marcar-radicada", json={"numero_radicado": "RAD-1"})
        assert r.status_code == 404

    def test_persiste_evidencia_y_workflow(self, client, db_session):
        g = _seed(db_session)
        r = client.post(
            f"/glosas/{g.id}/marcar-radicada",
            json={
                "numero_radicado": "RAD-2026-001",
                "fecha_radicacion": "2026-06-09",
                "observacion": "Radicada por portal web SANITAS, confirmación correo",
            },
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["numero_radicado"] == "RAD-2026-001"
        assert d["radicado_por"] == "coord@hus.com"
        assert d["workflow_anterior"] == "APROBADA"
        assert d["workflow_state"] == "RADICADA"
        assert d["radicado_en"].startswith("2026-06-09")

        db_session.refresh(g)
        assert g.numero_radicado == "RAD-2026-001"
        assert g.radicado_por == "coord@hus.com"
        assert g.radicado_observacion == "Radicada por portal web SANITAS, confirmación correo"
        assert g.radicado_en is not None
        assert g.workflow_state == "RADICADA"

    def test_sin_fecha_usa_ahora(self, client, db_session):
        g = _seed(db_session)
        r = client.post(f"/glosas/{g.id}/marcar-radicada", json={"numero_radicado": "RAD-7"})
        assert r.status_code == 200
        db_session.refresh(g)
        assert g.radicado_en is not None
        assert g.radicado_en.date() == ahora_utc().date()

    def test_escribe_audit_log(self, client, db_session):
        g = _seed(db_session)
        client.post(
            f"/glosas/{g.id}/marcar-radicada",
            json={"numero_radicado": "RAD-AUD-9", "observacion": "evidencia correo"},
        )
        ev = (
            db_session.query(AuditLogRecord)
            .filter(
                AuditLogRecord.accion == "MARCAR_RADICADA",
                AuditLogRecord.registro_id == g.id,
            )
            .first()
        )
        assert ev is not None
        assert ev.tabla == "historial"
        assert ev.campo == "numero_radicado"
        assert ev.valor_nuevo == "RAD-AUD-9"
        assert "RAD-AUD-9" in ev.detalle
        assert "evidencia correo" in ev.detalle

    def test_re_marcar_conserva_anterior_en_audit(self, client, db_session):
        g = _seed(db_session, numero_radicado="RAD-VIEJO")
        r = client.post(f"/glosas/{g.id}/marcar-radicada", json={"numero_radicado": "RAD-NUEVO"})
        assert r.status_code == 200
        ev = (
            db_session.query(AuditLogRecord)
            .filter(AuditLogRecord.accion == "MARCAR_RADICADA")
            .first()
        )
        assert ev.valor_anterior == "RAD-VIEJO"
        assert ev.valor_nuevo == "RAD-NUEVO"

    def test_numero_vacio_422_o_400(self, client, db_session):
        g = _seed(db_session)
        r = client.post(f"/glosas/{g.id}/marcar-radicada", json={"numero_radicado": ""})
        assert r.status_code in (400, 422)
        r2 = client.post(f"/glosas/{g.id}/marcar-radicada", json={"numero_radicado": "   "})
        assert r2.status_code == 400

    def test_auditor_propio_ok_ajeno_403(self, db_session):
        from app.main import app

        auditor = UsuarioRecord(id=2, email="gestor@hus.com", rol="AUDITOR", activo=1)
        propia = _seed(db_session, auditor_email="gestor@hus.com")
        ajena = _seed(db_session, auditor_email="otro@hus.com", factura="HUS999")
        sin_asignar = _seed(db_session, auditor_email=None, factura="HUS555")
        with _client_con(db_session, auditor) as c:
            ok = c.post(f"/glosas/{propia.id}/marcar-radicada", json={"numero_radicado": "R1"})
            assert ok.status_code == 200
            libre = c.post(
                f"/glosas/{sin_asignar.id}/marcar-radicada", json={"numero_radicado": "R2"}
            )
            assert libre.status_code == 200
            denegado = c.post(f"/glosas/{ajena.id}/marcar-radicada", json={"numero_radicado": "R3"})
            assert denegado.status_code == 403
        app.dependency_overrides.clear()

    def test_viewer_403(self, db_session):
        from app.main import app

        viewer = UsuarioRecord(id=3, email="viewer@hus.com", rol="VIEWER", activo=1)
        g = _seed(db_session)
        with _client_con(db_session, viewer) as c:
            r = c.post(f"/glosas/{g.id}/marcar-radicada", json={"numero_radicado": "R9"})
            assert r.status_code == 403
        app.dependency_overrides.clear()
