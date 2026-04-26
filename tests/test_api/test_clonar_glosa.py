"""Tests del endpoint POST /glosas/{id}/clonar (R65 P1)."""
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
def usuario_auditor():
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def glosa_origen(db_session):
    g = GlosaRecord(
        eps="FAMISANAR", paciente="JUAN PEREZ",
        codigo_glosa="TA0201", valor_objetado=168_563, valor_aceptado=50_000,
        etapa="RESPUESTA", estado="RESPONDIDA",
        dictamen="<div>dictamen completo</div>",
        modelo_ia="anthropic/claude-sonnet-4-6", score=85.0,
        numero_radicado="RAD-9", factura="FE-001",
        texto_glosa_original="TA0201 — diferencia tarifa CUPS 890750",
        cups_servicio="890750", servicio_descripcion="CONSULTA URGENCIAS",
        concepto_glosa="TARIFAS",
        creado_en=ahora_utc(),
    )
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    return g


@pytest.fixture
def client(db_session, usuario_auditor):
    from app.api.deps import get_auditor_o_superior, get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_auditor
    app.dependency_overrides[get_auditor_o_superior] = lambda: usuario_auditor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestClonarGlosa:
    def test_clona_y_devuelve_id_nuevo(self, client, glosa_origen, db_session):
        r = client.post(f"/glosas/{glosa_origen.id}/clonar")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id_origen"] == glosa_origen.id
        assert d["id_nueva"] != glosa_origen.id
        assert d["estado"] == "BORRADOR"
        # En BD existe nueva fila
        assert db_session.query(GlosaRecord).count() == 2

    def test_copia_campos_descriptivos(self, client, glosa_origen, db_session):
        r = client.post(f"/glosas/{glosa_origen.id}/clonar")
        nueva_id = r.json()["id_nueva"]
        nueva = db_session.query(GlosaRecord).filter_by(id=nueva_id).first()
        assert nueva.eps == "FAMISANAR"
        assert nueva.paciente == "JUAN PEREZ"
        assert nueva.codigo_glosa == "TA0201"
        assert nueva.factura == "FE-001"
        assert nueva.cups_servicio == "890750"
        assert nueva.servicio_descripcion == "CONSULTA URGENCIAS"
        assert nueva.concepto_glosa == "TARIFAS"

    def test_no_copia_dictamen_ni_decision(self, client, glosa_origen, db_session):
        """REGRESIÓN: la clonada NO debe heredar el dictamen de la
        original — sería confuso (es una glosa nueva, no la misma)."""
        r = client.post(f"/glosas/{glosa_origen.id}/clonar")
        nueva_id = r.json()["id_nueva"]
        nueva = db_session.query(GlosaRecord).filter_by(id=nueva_id).first()
        assert nueva.dictamen is None
        assert nueva.modelo_ia is None
        assert nueva.score == 0
        assert nueva.estado == "BORRADOR"

    def test_no_copia_valores_monetarios(self, client, glosa_origen, db_session):
        """Valores en 0 fuerzan al gestor a digitarlos según el caso nuevo."""
        r = client.post(f"/glosas/{glosa_origen.id}/clonar")
        nueva_id = r.json()["id_nueva"]
        nueva = db_session.query(GlosaRecord).filter_by(id=nueva_id).first()
        assert nueva.valor_objetado == 0
        assert nueva.valor_aceptado == 0

    def test_clonar_glosa_inexistente(self, client):
        r = client.post("/glosas/999999/clonar")
        assert r.status_code == 404

    def test_clonar_genera_audit_entry(self, client, glosa_origen, db_session):
        from app.models.db import AuditLogRecord
        r = client.post(f"/glosas/{glosa_origen.id}/clonar")
        nueva_id = r.json()["id_nueva"]
        # Debe existir entry CLONAR_GLOSA en audit_log
        log = (
            db_session.query(AuditLogRecord)
            .filter_by(accion="CLONAR_GLOSA", registro_id=nueva_id).first()
        )
        assert log is not None
        assert "Clonada desde" in (log.detalle or "")
