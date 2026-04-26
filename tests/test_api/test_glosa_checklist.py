"""Tests del endpoint GET /glosas/{id}/checklist (R96 P1)."""
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


class TestGlosaChecklist:
    def test_404(self, client):
        r = client.get("/glosas/99999/checklist")
        assert r.status_code == 404

    def test_glosa_minima_pocos_completos(self, client, db_session):
        g = _seed(db_session, factura="N/A", texto_glosa_original=None)
        r = client.get(f"/glosas/{g.id}/checklist")
        assert r.status_code == 200, r.text
        d = r.json()
        # Solo valor_objetado>0 está completo entre los obligatorios
        items_dict = {it["id"]: it for it in d["items"]}
        assert items_dict["valor_objetado"]["completado"] is True
        assert items_dict["texto_original"]["completado"] is False
        assert items_dict["factura"]["completado"] is False
        assert items_dict["dictamen"]["completado"] is False
        assert items_dict["respuesta_eps"]["completado"] is False
        assert items_dict["cierre"]["completado"] is False
        assert d["porcentaje_avance"] < 50.0

    def test_glosa_completa(self, client, db_session):
        g = _seed(db_session,
                  factura="F-001",
                  texto_glosa_original="texto largo de la glosa original",
                  valor_objetado=5000,
                  dictamen="<p>" + ("dictamen detallado " * 10) + "</p>",
                  gestor_nombre="Alice",
                  auditor_email="auditor@hus.com",
                  fecha_recepcion=ahora_utc(),
                  decision_eps="ACEPTA",
                  estado="LEVANTADA")
        r = client.get(f"/glosas/{g.id}/checklist")
        d = r.json()
        # Todos los items obligatorios completados
        assert d["obligatorios_pendientes"] == 0
        assert d["porcentaje_avance"] == 100.0
        assert d["completados"] == d["total_items"]

    def test_estructura_items(self, client, db_session):
        g = _seed(db_session)
        r = client.get(f"/glosas/{g.id}/checklist")
        d = r.json()
        for it in d["items"]:
            assert "id" in it
            assert "descripcion" in it
            assert "completado" in it
            assert "opcional" in it
            assert isinstance(it["completado"], bool)
            assert isinstance(it["opcional"], bool)

    def test_porcentaje_solo_obligatorios(self, client, db_session):
        # Glosa con TODOS los opcionales completos pero ningún obligatorio
        g = _seed(db_session, valor_objetado=0,
                  factura="N/A",
                  texto_glosa_original=None,
                  dictamen=None,
                  gestor_nombre="Alice",
                  auditor_email="auditor@hus.com",
                  fecha_recepcion=ahora_utc())
        r = client.get(f"/glosas/{g.id}/checklist")
        d = r.json()
        # Los opcionales no inflan el %
        assert d["porcentaje_avance"] == 0.0
