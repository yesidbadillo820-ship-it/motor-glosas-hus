"""Tests del endpoint GET /admin/reporte-mensual.csv (R126 P2)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AICallRecord, GlosaRecord, UsuarioRecord


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
def usuario_super(db_session):
    u = UsuarioRecord(
        id=1, email="root@hus.gov.co", rol="SUPER_ADMIN", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_super):
    from app.api.deps import get_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_admin] = lambda: usuario_super
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_glosa(db, creado, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
    )
    base.update(kw)
    db.add(GlosaRecord(creado_en=creado, **base))
    db.commit()


def _seed_ia(db, creado, cost=0.01):
    db.add(AICallRecord(
        proveedor="anthropic", modelo="claude",
        cost_usd=cost, creado_en=creado,
    ))
    db.commit()


class TestReporteMensualCSV:
    def test_csv_content_type(self, client, db_session):
        _seed_glosa(db_session, ahora_utc())
        r = client.get("/admin/reporte-mensual.csv")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]

    def test_header_row(self, client):
        r = client.get("/admin/reporte-mensual.csv")
        primera = r.text.split("\n")[0]
        for col in ("mes", "glosas_creadas", "glosas_cerradas",
                    "valor_objetado", "valor_recuperado",
                    "tasa_levantamiento_pct", "tasa_recuperacion_pct",
                    "ia_calls", "costo_ia_usd"):
            assert col in primera

    def test_serie_por_mes(self, client, db_session):
        _seed_glosa(db_session,
                    datetime(2026, 3, 15, tzinfo=timezone.utc))
        _seed_glosa(db_session,
                    datetime(2026, 4, 1, tzinfo=timezone.utc))
        _seed_glosa(db_session,
                    datetime(2026, 4, 20, tzinfo=timezone.utc))

        r = client.get("/admin/reporte-mensual.csv")
        # 1 header + 2 meses = 3 líneas no vacías
        lineas = [l for l in r.text.strip().split("\n") if l]
        assert len(lineas) == 3
        # Marzo aparece con 1 glosa
        assert any("2026-03,1" in l for l in lineas)
        # Abril con 2
        assert any("2026-04,2" in l for l in lineas)

    def test_incluye_costos_ia(self, client, db_session):
        _seed_ia(db_session,
                 datetime(2026, 4, 5, tzinfo=timezone.utc),
                 cost=2.5)
        r = client.get("/admin/reporte-mensual.csv")
        assert "2.5" in r.text
