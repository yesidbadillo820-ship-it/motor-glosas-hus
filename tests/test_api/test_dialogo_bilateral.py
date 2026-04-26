"""Tests del endpoint GET /glosas/{id}/dialogo-bilateral (R138 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import ConciliacionRecord, GlosaRecord, UsuarioRecord


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


def _seed_glosa(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


class TestDialogoBilateral:
    def test_404(self, client):
        r = client.get("/glosas/99999/dialogo-bilateral")
        assert r.status_code == 404

    def test_glosa_minima_solo_objecion(self, client, db_session):
        g = _seed_glosa(db_session)
        r = client.get(f"/glosas/{g.id}/dialogo-bilateral")
        d = r.json()
        # Sin dictamen, sin decisión → solo paso 1 (EPS objeta)
        assert d["total_pasos"] == 1
        assert d["dialogo"][0]["actor"] == "EPS"

    def test_dialogo_completo(self, client, db_session):
        g = _seed_glosa(
            db_session,
            dictamen="<p>" + "argumentación " * 20 + "</p>",
            decision_eps="ACEPTA",
            valor_recuperado=5000,
            fecha_decision_eps=ahora_utc(),
            estado="LEVANTADA",
            codigo_respuesta="RE9901",
        )
        r = client.get(f"/glosas/{g.id}/dialogo-bilateral")
        d = r.json()
        # 3 pasos: objeción + respuesta HUS + decisión EPS
        assert d["total_pasos"] == 3
        actores = [p["actor"] for p in d["dialogo"]]
        assert actores == ["EPS", "HUS", "EPS"]

    def test_incluye_conciliacion(self, client, db_session):
        g = _seed_glosa(db_session)
        db_session.add(ConciliacionRecord(
            glosa_id=g.id,
            creado_en=ahora_utc(),
            resultado="ACUERDO",
            valor_conciliado=2500,
            estado_bilateral="ACTA_FIRMADA",
        ))
        db_session.commit()

        r = client.get(f"/glosas/{g.id}/dialogo-bilateral")
        d = r.json()
        actores = [p["actor"] for p in d["dialogo"]]
        assert "BILATERAL" in actores
        bilateral = next(p for p in d["dialogo"] if p["actor"] == "BILATERAL")
        assert "ACUERDO" in bilateral["mensaje"]

    def test_mensaje_objecion_incluye_codigo_y_valor(self, client, db_session):
        g = _seed_glosa(db_session,
                        codigo_glosa="TA0201",
                        valor_objetado=15000)
        r = client.get(f"/glosas/{g.id}/dialogo-bilateral")
        d = r.json()
        msg = d["dialogo"][0]["mensaje"]
        assert "TA0201" in msg
        assert "15,000" in msg
