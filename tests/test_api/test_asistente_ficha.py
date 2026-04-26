"""Tests del endpoint GET /glosas/{id}/asistente-ficha (R370 P1)."""
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
    return UsuarioRecord(
        id=1, email="auditor@hus.com", rol="AUDITOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gid, eps="X", codigo="C", estado="RADICADA",
          dictamen=None, dias=10, codigo_respuesta=None,
          factura="F1"):
    db.add(GlosaRecord(
        id=gid,
        eps=eps, paciente="X", codigo_glosa=codigo, factura=factura,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dictamen=dictamen,
        dias_restantes=dias,
        codigo_respuesta=codigo_respuesta,
        fecha_decision_eps=(
            ahora_utc() if estado in ("LEVANTADA","RATIFICADA","ACEPTADA") else None
        ),
    ))
    db.commit()


class TestAsistenteFicha:
    def test_combina_senales(self, db_session, client):
        # Glosa abierta
        _seed(db_session, 1, dictamen=None, dias=2)
        # Histórico: 2 LEV con RE9501, 1 RAT con RE9701
        _seed(
            db_session, 2, estado="LEVANTADA",
            codigo_respuesta="RE9501",
        )
        _seed(
            db_session, 3, estado="LEVANTADA",
            codigo_respuesta="RE9501",
        )
        _seed(
            db_session, 4, estado="RATIFICADA",
            codigo_respuesta="RE9701",
        )

        r = client.get("/glosas/1/asistente-ficha")
        d = r.json()
        # Probabilidad calculada
        assert d["probabilidad"]["tasa_par_eps_codigo_pct"] is not None
        # codigo respuesta sugerido es el de mejor tasa con 2+ muestras
        assert d["codigo_respuesta_sugerido"]["codigo_respuesta"] == "RE9501"
        # Alerta de dictamen vacío
        assert d["alerta_dictamen"] is not None
        # Urgencia crítica (2 días)
        assert d["urgencia"]["nivel"] == "CRITICA"
        # Acciones sugeridas no vacías
        assert len(d["acciones_sugeridas"]) > 0

    def test_404(self, client):
        r = client.get("/glosas/999/asistente-ficha")
        assert r.status_code == 404
