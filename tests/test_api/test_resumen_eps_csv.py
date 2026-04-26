"""Tests del endpoint GET /glosas/exportar-resumen-eps.csv (R236 P1)."""
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


def _seed(db, eps, estado="RADICADA", obj=1000, rec=0):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=obj, valor_recuperado=rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestResumenEPSCSV:
    def test_csv_content_type(self, client):
        r = client.get("/glosas/exportar-resumen-eps.csv")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]

    def test_header(self, client):
        r = client.get("/glosas/exportar-resumen-eps.csv")
        primera = r.text.split("\n")[0]
        for col in ("eps", "total_glosas", "abiertas",
                    "tasa_levantamiento_pct"):
            assert col in primera

    def test_filas_correctas(self, client, db_session):
        _seed(db_session, "ALPHA", estado="RADICADA")
        _seed(db_session, "ALPHA", estado="LEVANTADA", rec=5000)
        _seed(db_session, "BETA", estado="ACEPTADA")

        r = client.get("/glosas/exportar-resumen-eps.csv")
        lineas = [l for l in r.text.strip().split("\n") if l]
        # 1 header + 2 EPS = 3
        assert len(lineas) == 3
        # Orden alfabético: ALPHA antes que BETA
        assert lineas[1].startswith("ALPHA")
