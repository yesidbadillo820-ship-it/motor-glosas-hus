"""Tests del endpoint /glosas/bulk-actualizar-estado (R71 P1)."""
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


@pytest.fixture
def usuario_auditor():
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


def _seed_n_glosas(db, n):
    ids = []
    for i in range(n):
        g = GlosaRecord(
            eps="X", paciente=f"P{i}", codigo_glosa="TA0201",
            valor_objetado=100, etapa="X", estado="RADICADA",
            creado_en=ahora_utc(),
        )
        db.add(g)
        db.commit()
        db.refresh(g)
        ids.append(g.id)
    return ids


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


class TestBulkActualizarEstado:
    def test_actualiza_todas_existentes(self, client, db_session):
        ids = _seed_n_glosas(db_session, 3)
        r = client.post("/glosas/bulk-actualizar-estado", json={
            "glosa_ids": ids,
            "nuevo_estado": "LEVANTADA",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["actualizadas"] == 3
        assert d["no_encontradas"] == []
        # Verificar en BD
        for gid in ids:
            g = db_session.query(GlosaRecord).filter_by(id=gid).first()
            assert g.estado == "LEVANTADA"

    def test_glosas_no_encontradas_se_listan(self, client, db_session):
        ids = _seed_n_glosas(db_session, 2)
        r = client.post("/glosas/bulk-actualizar-estado", json={
            "glosa_ids": ids + [99999, 88888],
            "nuevo_estado": "RATIFICADA",
        })
        d = r.json()
        assert d["actualizadas"] == 2
        assert sorted(d["no_encontradas"]) == [88888, 99999]

    def test_estado_invalido_422(self, client, db_session):
        ids = _seed_n_glosas(db_session, 1)
        r = client.post("/glosas/bulk-actualizar-estado", json={
            "glosa_ids": ids,
            "nuevo_estado": "INVENTADO_NO_EXISTE",
        })
        assert r.status_code == 422

    def test_lista_vacia_falla(self, client):
        r = client.post("/glosas/bulk-actualizar-estado", json={
            "glosa_ids": [],
            "nuevo_estado": "LEVANTADA",
        })
        # Pydantic min_length=1
        assert r.status_code == 422

    def test_cap_500(self, client):
        r = client.post("/glosas/bulk-actualizar-estado", json={
            "glosa_ids": list(range(1, 502)),  # 501
            "nuevo_estado": "LEVANTADA",
        })
        assert r.status_code == 422

    def test_audit_log_por_cada_actualizacion(self, client, db_session):
        ids = _seed_n_glosas(db_session, 3)
        r = client.post("/glosas/bulk-actualizar-estado", json={
            "glosa_ids": ids,
            "nuevo_estado": "ACEPTADA",
            "nota": "Decisión EPS de marzo",
        })
        assert r.status_code == 200
        # 3 entries de BULK_UPDATE_ESTADO
        logs = db_session.query(AuditLogRecord).filter_by(
            accion="BULK_UPDATE_ESTADO",
        ).all()
        assert len(logs) == 3
        assert all(l.valor_nuevo == "ACEPTADA" for l in logs)
        assert all("Decisión EPS de marzo" in (l.detalle or "") for l in logs)
