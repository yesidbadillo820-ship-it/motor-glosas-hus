"""Tests del endpoint GET /glosas/stats/recuperacion-mensual (R97 P2)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def _seed(db, fecha_dec, valor_objetado, valor_rec):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor_objetado, valor_recuperado=valor_rec,
        etapa="X", estado="LEVANTADA",
        creado_en=ahora_utc(),
        fecha_decision_eps=fecha_dec,
    ))
    db.commit()


class TestRecuperacionMensual:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/recuperacion-mensual")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["serie"] == []
        assert d["total_recuperado"] == 0

    def test_serie_agrupa_por_mes(self, client, db_session):
        # Hoy es 2026-04-26 según contexto
        _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc), 10000, 8000)
        _seed(db_session, datetime(2026, 4, 15, tzinfo=timezone.utc), 5000, 5000)
        _seed(db_session, datetime(2026, 3, 10, tzinfo=timezone.utc), 20000, 10000)

        r = client.get("/glosas/stats/recuperacion-mensual")
        d = r.json()
        # 2 meses distintos
        assert len(d["serie"]) == 2
        meses = {s["mes"]: s for s in d["serie"]}
        assert meses["2026-04"]["glosas_cerradas"] == 2
        assert meses["2026-04"]["recuperado"] == 13000
        assert meses["2026-03"]["recuperado"] == 10000

    def test_tasa_recuperacion(self, client, db_session):
        _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc), 10000, 5000)
        r = client.get("/glosas/stats/recuperacion-mensual")
        d = r.json()
        assert d["serie"][0]["tasa_recuperacion_pct"] == 50.0

    def test_serie_ordenada_ascendentemente(self, client, db_session):
        _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc), 1000, 500)
        _seed(db_session, datetime(2026, 1, 1, tzinfo=timezone.utc), 1000, 500)
        _seed(db_session, datetime(2026, 3, 1, tzinfo=timezone.utc), 1000, 500)
        r = client.get("/glosas/stats/recuperacion-mensual")
        d = r.json()
        meses = [s["mes"] for s in d["serie"]]
        assert meses == sorted(meses)

    def test_excluye_sin_fecha_decision(self, client, db_session):
        # Glosa SIN fecha_decision_eps → no entra en el cómputo
        db_session.add(GlosaRecord(
            eps="X", paciente="X", codigo_glosa="C",
            valor_objetado=1000, valor_recuperado=500,
            etapa="X", estado="LEVANTADA",
            creado_en=ahora_utc(),
            fecha_decision_eps=None,
        ))
        db_session.commit()

        r = client.get("/glosas/stats/recuperacion-mensual")
        d = r.json()
        assert d["serie"] == []
