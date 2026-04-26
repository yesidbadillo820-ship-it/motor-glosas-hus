"""Tests del endpoint GET /contratos/{eps}/perfil-detallado (R121 P2)."""
from __future__ import annotations

from datetime import timedelta

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


def _seed(db, eps, **kw):
    base = dict(
        paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(eps=eps, **base))
    db.commit()


class TestPerfilDetalladoEPS:
    def test_eps_sin_historial(self, client):
        r = client.get("/contratos/SANITAS/perfil-detallado")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["sin_historial"] is True
        assert d["total_glosas"] == 0

    def test_estructura_completa(self, client, db_session):
        _seed(db_session, "SANITAS", estado="LEVANTADA",
              valor_objetado=5000, valor_recuperado=5000)
        r = client.get("/contratos/SANITAS/perfil-detallado")
        d = r.json()
        assert d["sin_historial"] is False
        for sec in ("volumen", "economico", "resoluciones",
                    "top_5_codigos_objetados",
                    "codigos_respuesta_efectivos",
                    "ultima_actividad"):
            assert sec in d

    def test_volumen_correcto(self, client, db_session):
        _seed(db_session, "X", estado="RADICADA")
        _seed(db_session, "X", estado="LEVANTADA")
        _seed(db_session, "X", estado="ACEPTADA")
        r = client.get("/contratos/X/perfil-detallado")
        d = r.json()
        assert d["volumen"]["total_glosas"] == 3
        assert d["volumen"]["abiertas"] == 1
        assert d["volumen"]["cerradas"] == 2
        assert d["volumen"]["decididas"] == 2
        assert d["volumen"]["levantadas"] == 1

    def test_top_codigos(self, client, db_session):
        _seed(db_session, "X", codigo_glosa="TA0201")
        _seed(db_session, "X", codigo_glosa="TA0201")
        _seed(db_session, "X", codigo_glosa="FA0603")
        r = client.get("/contratos/X/perfil-detallado")
        d = r.json()
        top = d["top_5_codigos_objetados"]
        assert top[0] == {"codigo": "TA0201", "veces": 2}
        assert top[1] == {"codigo": "FA0603", "veces": 1}

    def test_codigos_respuesta_efectivos(self, client, db_session):
        # RE9502 usado 2x, 100% éxito
        _seed(db_session, "X", estado="LEVANTADA", codigo_respuesta="RE9502")
        _seed(db_session, "X", estado="LEVANTADA", codigo_respuesta="RE9502")
        # RE9801 usado 1x, 0% éxito
        _seed(db_session, "X", estado="RATIFICADA", codigo_respuesta="RE9801")
        r = client.get("/contratos/X/perfil-detallado")
        d = r.json()
        eff = d["codigos_respuesta_efectivos"]
        assert eff[0]["codigo_respuesta"] == "RE9502"
        assert eff[0]["tasa_exito_pct"] == 100.0

    def test_aislamiento_por_eps(self, client, db_session):
        _seed(db_session, "EPS_A", valor_objetado=999)
        _seed(db_session, "EPS_B", valor_objetado=1)
        r = client.get("/contratos/EPS_A/perfil-detallado")
        d = r.json()
        assert d["volumen"]["total_glosas"] == 1
        assert d["economico"]["valor_objetado_total"] == 999
