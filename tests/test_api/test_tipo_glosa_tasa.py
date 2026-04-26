"""Tests del endpoint GET /glosas/stats/tipo-glosa-tasa (R308 P1)."""
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


def _seed(db, codigo, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestTipoGlosaTasa:
    def test_calcula(self, client, db_session):
        _seed(db_session, "TA0801", "LEVANTADA")
        _seed(db_session, "TA0802", "LEVANTADA")
        _seed(db_session, "TA0803", "RATIFICADA")
        # TA: 2 LEV / 3 dec → 66.67%
        _seed(db_session, "FA0603", "RATIFICADA")
        # FA: 0 / 1 → 0%

        r = client.get("/glosas/stats/tipo-glosa-tasa")
        d = r.json()
        items = {it["tipo"]: it for it in d["items"]}
        assert items["TA"]["decididas"] == 3
        assert items["TA"]["levantadas"] == 2
        assert items["TA"]["tasa_levantamiento_pct"] == 66.67
        assert items["FA"]["tasa_levantamiento_pct"] == 0.0
