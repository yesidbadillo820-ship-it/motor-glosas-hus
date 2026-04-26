"""Tests del endpoint GET /glosas/{id}/score-prioridad (R112 P2)."""
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
        valor_objetado=100, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        dictamen="<p>" + "x" * 100 + "</p>",
        gestor_nombre="Alice",
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


class TestScorePrioridad:
    def test_404(self, client):
        r = client.get("/glosas/99999/score-prioridad")
        assert r.status_code == 404

    def test_cerrada_score_cero(self, client, db_session):
        g = _seed(db_session, estado="LEVANTADA")
        r = client.get(f"/glosas/{g.id}/score-prioridad")
        d = r.json()
        assert d["score_total"] == 0
        assert d["banner_recomendado"] == "INFO"
        assert d["desglose"] == []

    def test_vencida_urgente(self, client, db_session):
        g = _seed(db_session, dias_restantes=-10)
        r = client.get(f"/glosas/{g.id}/score-prioridad")
        d = r.json()
        # vencimiento +100 → URGENTE (>=100)
        assert d["score_total"] >= 100
        assert d["banner_recomendado"] == "URGENTE"

    def test_critica_alta(self, client, db_session):
        g = _seed(db_session, dias_restantes=2)
        r = client.get(f"/glosas/{g.id}/score-prioridad")
        d = r.json()
        # crítica +50 → ALTA (50-99)
        assert 50 <= d["score_total"] < 100
        assert d["banner_recomendado"] == "ALTA"

    def test_solo_sin_dictamen_media(self, client, db_session):
        g = _seed(db_session, dias_restantes=20, dictamen=None)
        r = client.get(f"/glosas/{g.id}/score-prioridad")
        d = r.json()
        # sin dictamen +25 → MEDIA (25-49)
        assert d["score_total"] == 25
        assert d["banner_recomendado"] == "MEDIA"

    def test_glosa_buena_info(self, client, db_session):
        g = _seed(db_session, dias_restantes=20, valor_objetado=100,
                  dictamen="x" * 100, gestor_nombre="Alice")
        r = client.get(f"/glosas/{g.id}/score-prioridad")
        d = r.json()
        # Sin componentes activos → score 0 → INFO
        assert d["score_total"] == 0
        assert d["banner_recomendado"] == "INFO"

    def test_desglose_estructura(self, client, db_session):
        g = _seed(db_session, dias_restantes=-5,
                  valor_objetado=20_000_000)
        r = client.get(f"/glosas/{g.id}/score-prioridad")
        d = r.json()
        for item in d["desglose"]:
            assert "componente" in item
            assert "peso" in item
            assert "razon" in item
