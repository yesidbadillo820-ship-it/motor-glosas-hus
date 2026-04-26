"""Tests del endpoint /glosas/{id}/paquete-evidencia.json (R85 P2)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    AICallRecord, AuditLogRecord, GlosaRecord, UsuarioRecord,
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
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def glosa(db_session):
    g = GlosaRecord(
        eps="FAMISANAR", paciente="JUAN", codigo_glosa="TA0201",
        valor_objetado=168_563, etapa="X", estado="RADICADA",
        factura="FE-001",
        dictamen="<p>Dictamen formal del HUS</p>",
        modelo_ia="anthropic/claude-sonnet-4-6",
        creado_en=ahora_utc(),
    )
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    return g


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestPaqueteEvidencia:
    def test_404_glosa_inexistente(self, client):
        r = client.get("/glosas/99999/paquete-evidencia.json")
        assert r.status_code == 404

    def test_estructura_completa(self, client, glosa):
        r = client.get(f"/glosas/{glosa.id}/paquete-evidencia.json")
        assert r.status_code == 200
        d = json.loads(r.text)
        for k in ("metadata", "glosa", "dictamen_actual", "timeline", "ia_calls"):
            assert k in d

    def test_glosa_data_completa(self, client, glosa):
        r = client.get(f"/glosas/{glosa.id}/paquete-evidencia.json")
        d = json.loads(r.text)
        g = d["glosa"]
        assert g["eps"] == "FAMISANAR"
        assert g["codigo_glosa"] == "TA0201"
        assert g["valor_objetado"] == 168_563

    def test_dictamen_actual_incluye_firma(self, client, glosa):
        r = client.get(f"/glosas/{glosa.id}/paquete-evidencia.json")
        d = json.loads(r.text)
        firma = d["dictamen_actual"]
        assert firma is not None
        assert "hash" in firma
        assert "firma" in firma
        assert "alg" in firma
        assert "texto_dictamen_html" in firma

    def test_sin_dictamen_firma_es_none(self, client, db_session):
        g = GlosaRecord(
            eps="X", paciente="X", codigo_glosa="TA0201",
            valor_objetado=100, etapa="X", estado="RADICADA",
            dictamen=None, creado_en=ahora_utc(),
        )
        db_session.add(g)
        db_session.commit()
        r = client.get(f"/glosas/{g.id}/paquete-evidencia.json")
        d = json.loads(r.text)
        assert d["dictamen_actual"] is None

    def test_timeline_incluye_audit_y_calls(self, client, glosa, db_session):
        db_session.add(AuditLogRecord(
            tabla="glosas", registro_id=glosa.id,
            accion="ACTUALIZAR_ESTADO", usuario_email="x@hus.com",
            timestamp=ahora_utc(),
        ))
        db_session.add(AICallRecord(
            glosa_id=glosa.id, proveedor="anthropic",
            modelo="claude-sonnet-4-6", cost_usd=0.045,
            input_tokens=8000, output_tokens=500,
            creado_en=ahora_utc(),
        ))
        db_session.commit()
        r = client.get(f"/glosas/{glosa.id}/paquete-evidencia.json")
        d = json.loads(r.text)
        # Timeline incluye audit
        tipos = [e["tipo"] for e in d["timeline"]]
        assert "AUDIT_ACTUALIZAR_ESTADO" in tipos
        # ia_calls incluye el call
        assert len(d["ia_calls"]) >= 1

    def test_descarga_attachment(self, client, glosa):
        r = client.get(f"/glosas/{glosa.id}/paquete-evidencia.json")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".json" in cd
