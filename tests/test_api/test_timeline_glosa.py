"""Tests del endpoint GET /glosas/{id}/timeline (R67 P2)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    AICallRecord, AuditLogRecord, ComentarioGlosaRecord,
    DictamenVersionRecord, GlosaRecord, UsuarioRecord,
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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def glosa(db_session):
    g = GlosaRecord(
        eps="FAMISANAR", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100_000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc() - timedelta(days=2),
        auditor_email="x@hus.com",
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


class TestTimelineGlosa:
    def test_glosa_inexistente_404(self, client):
        r = client.get("/glosas/99999/timeline")
        assert r.status_code == 404

    def test_glosa_recien_creada_solo_evento_creacion(self, client, glosa):
        r = client.get(f"/glosas/{glosa.id}/timeline")
        assert r.status_code == 200
        d = r.json()
        assert d["glosa_id"] == glosa.id
        assert d["total_eventos"] == 1
        assert d["eventos"][0]["tipo"] == "CREAR_GLOSA"

    def test_timeline_combina_versiones(self, client, glosa, db_session):
        db_session.add(DictamenVersionRecord(
            glosa_id=glosa.id, dictamen_html="<p>v1</p>",
            accion="CREAR", autor_email="x@hus.com",
            creado_en=ahora_utc() - timedelta(hours=2),
        ))
        db_session.add(DictamenVersionRecord(
            glosa_id=glosa.id, dictamen_html="<p>v2 reanalizado</p>",
            accion="REANALIZAR", autor_email="x@hus.com",
            creado_en=ahora_utc() - timedelta(hours=1),
        ))
        db_session.commit()
        r = client.get(f"/glosas/{glosa.id}/timeline")
        d = r.json()
        tipos = [e["tipo"] for e in d["eventos"]]
        assert "VERSION_CREAR" in tipos
        assert "VERSION_REANALIZAR" in tipos

    def test_timeline_combina_audit(self, client, glosa, db_session):
        db_session.add(AuditLogRecord(
            usuario_email="x@hus.com", usuario_rol="AUDITOR",
            accion="ACTUALIZAR_ESTADO", tabla="glosas",
            registro_id=glosa.id,
            campo="estado", valor_anterior="RADICADA", valor_nuevo="RESPONDIDA",
            timestamp=ahora_utc() - timedelta(minutes=30),
        ))
        db_session.commit()
        r = client.get(f"/glosas/{glosa.id}/timeline")
        d = r.json()
        tipos = [e["tipo"] for e in d["eventos"]]
        assert "AUDIT_ACTUALIZAR_ESTADO" in tipos

    def test_timeline_combina_calls_ia(self, client, glosa, db_session):
        db_session.add(AICallRecord(
            glosa_id=glosa.id, proveedor="anthropic",
            modelo="claude-sonnet-4-6", latency_ms=2500,
            input_tokens=8000, output_tokens=500, cost_usd=0.045,
            creado_en=ahora_utc() - timedelta(seconds=10),
        ))
        db_session.commit()
        r = client.get(f"/glosas/{glosa.id}/timeline")
        d = r.json()
        ai_events = [e for e in d["eventos"] if e["tipo"] == "AI_CALL"]
        assert len(ai_events) == 1
        assert "claude-sonnet-4-6" in ai_events[0]["detalle"]

    def test_timeline_orden_desc(self, client, glosa, db_session):
        """Más reciente primero."""
        db_session.add(DictamenVersionRecord(
            glosa_id=glosa.id, dictamen_html="<p>antiguo</p>",
            accion="CREAR", autor_email="x@hus.com",
            creado_en=ahora_utc() - timedelta(hours=5),
        ))
        db_session.add(DictamenVersionRecord(
            glosa_id=glosa.id, dictamen_html="<p>nuevo</p>",
            accion="REFINAR", autor_email="x@hus.com",
            creado_en=ahora_utc(),
        ))
        db_session.commit()
        r = client.get(f"/glosas/{glosa.id}/timeline")
        d = r.json()
        # Primer evento debe ser el más reciente
        ts = [e["timestamp"] for e in d["eventos"]]
        ts_sorted = sorted(ts, reverse=True)
        assert ts == ts_sorted

    def test_timeline_comentarios(self, client, glosa, db_session):
        c = ComentarioGlosaRecord(
            glosa_id=glosa.id, autor_email="x@hus.com",
            texto="¿Por qué se aceptó parcial?",
            creado_en=ahora_utc() - timedelta(minutes=20),
        )
        db_session.add(c)
        db_session.commit()
        r = client.get(f"/glosas/{glosa.id}/timeline")
        d = r.json()
        tipos = [e["tipo"] for e in d["eventos"]]
        assert "COMENTARIO" in tipos
