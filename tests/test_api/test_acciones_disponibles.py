"""Tests del endpoint /glosas/{id}/acciones-disponibles (R78 P1)."""
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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    g = GlosaRecord(**base)
    db.add(g)
    db.commit()
    db.refresh(g)
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


class TestAccionesDisponibles:
    def test_glosa_inexistente_404(self, client):
        r = client.get("/glosas/99999/acciones-disponibles")
        assert r.status_code == 404

    def test_estructura_completa(self, client, db_session):
        g = _seed(db_session, dictamen="<p>" + "x" * 100 + "</p>")
        r = client.get(f"/glosas/{g.id}/acciones-disponibles")
        assert r.status_code == 200
        d = r.json()
        for k in ("glosa_id", "estado_actual", "transiciones_workflow",
                  "acciones_operativas", "sugerencia_principal"):
            assert k in d

    def test_sin_dictamen_no_descarga_pdf(self, client, db_session):
        g = _seed(db_session, dictamen=None)
        r = client.get(f"/glosas/{g.id}/acciones-disponibles")
        d = r.json()
        assert d["acciones_operativas"]["puede_descargar_pdf"] is False
        assert d["acciones_operativas"]["puede_refinar"] is False

    def test_con_dictamen_puede_descargar(self, client, db_session):
        g = _seed(db_session, dictamen="<p>" + "x" * 200 + "</p>")
        r = client.get(f"/glosas/{g.id}/acciones-disponibles")
        d = r.json()
        assert d["acciones_operativas"]["puede_descargar_pdf"] is True
        assert d["acciones_operativas"]["puede_refinar"] is True

    def test_sin_texto_original_no_puede_reanalizar(self, client, db_session):
        g = _seed(db_session, texto_glosa_original=None)
        r = client.get(f"/glosas/{g.id}/acciones-disponibles")
        d = r.json()
        assert d["acciones_operativas"]["puede_reanalizar"] is False

    def test_transiciones_radicada(self, client, db_session):
        g = _seed(db_session, estado="RADICADA")
        r = client.get(f"/glosas/{g.id}/acciones-disponibles")
        d = r.json()
        # Desde RADICADA → RESPONDIDA es la transición típica
        hacias = [t["hacia"] for t in d["transiciones_workflow"]]
        assert "RESPONDIDA" in hacias

    def test_sugerencia_urgente_vence_2_dias(self, client, db_session):
        g = _seed(
            db_session,
            estado="RADICADA",
            dictamen="<p>" + "x" * 100 + "</p>",
            dias_restantes=1,
        )
        r = client.get(f"/glosas/{g.id}/acciones-disponibles")
        d = r.json()
        assert "URGENTE" in (d["sugerencia_principal"] or "")

    def test_sugerencia_levantada_plantilla_gold(self, client, db_session):
        g = _seed(
            db_session,
            estado="LEVANTADA",
            dictamen="<p>" + "x" * 100 + "</p>",
        )
        r = client.get(f"/glosas/{g.id}/acciones-disponibles")
        d = r.json()
        assert "Gold" in (d["sugerencia_principal"] or "")
