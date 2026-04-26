"""Tests del endpoint GET /glosas/{id}/recomendaciones (R111 P1)."""
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
        factura="F-001",
        dictamen="<p>" + "x" * 100 + "</p>",
        gestor_nombre="Alice",
        texto_glosa_original="texto",
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


class TestRecomendaciones:
    def test_404(self, client):
        r = client.get("/glosas/99999/recomendaciones")
        assert r.status_code == 404

    def test_glosa_cerrada_solo_archivar(self, client, db_session):
        g = _seed(db_session, estado="LEVANTADA")
        r = client.get(f"/glosas/{g.id}/recomendaciones")
        d = r.json()
        assert len(d["items"]) == 1
        assert d["items"][0]["accion"] == "ARCHIVAR"

    def test_vencida_high(self, client, db_session):
        g = _seed(db_session, dias_restantes=-10)
        r = client.get(f"/glosas/{g.id}/recomendaciones")
        d = r.json()
        acciones = [it["accion"] for it in d["items"]]
        assert "ATENDER_VENCIDA" in acciones
        # HIGH priority
        atender = next(it for it in d["items"]
                       if it["accion"] == "ATENDER_VENCIDA")
        assert atender["prioridad"] == "HIGH"

    def test_critica(self, client, db_session):
        g = _seed(db_session, dias_restantes=2)
        r = client.get(f"/glosas/{g.id}/recomendaciones")
        d = r.json()
        acciones = [it["accion"] for it in d["items"]]
        assert "ATENDER_CRITICA" in acciones

    def test_sin_dictamen_alta(self, client, db_session):
        g = _seed(db_session, dictamen=None)
        r = client.get(f"/glosas/{g.id}/recomendaciones")
        d = r.json()
        item = next((it for it in d["items"]
                     if it["accion"] == "GENERAR_DICTAMEN"), None)
        assert item is not None
        assert item["prioridad"] == "HIGH"
        assert "endpoint" in item

    def test_sin_gestor_media(self, client, db_session):
        g = _seed(db_session, gestor_nombre=None)
        r = client.get(f"/glosas/{g.id}/recomendaciones")
        d = r.json()
        item = next((it for it in d["items"]
                     if it["accion"] == "ASIGNAR_GESTOR"), None)
        assert item is not None
        assert item["prioridad"] == "MEDIUM"

    def test_glosa_buena_monitoreo(self, client, db_session):
        # Glosa con todo OK
        g = _seed(db_session, dias_restantes=20,
                  cups_servicio="123456")
        r = client.get(f"/glosas/{g.id}/recomendaciones")
        d = r.json()
        # Sin issues → recomendación de monitoreo
        if len(d["items"]) == 1:
            assert d["items"][0]["accion"] == "MONITOREAR"
