"""Tests del endpoint GET /admin/glosas/exportar.csv (R116 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestAdminExportarGlosasCSV:
    def test_csv_content_type(self, client, db_session):
        _seed(db_session)
        r = client.get("/admin/glosas/exportar.csv")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]

    def test_header_row(self, client, db_session):
        r = client.get("/admin/glosas/exportar.csv")
        primera = r.text.split("\n")[0]
        for col in ("id", "creado_en", "eps", "factura", "codigo_glosa",
                    "valor_objetado", "valor_recuperado", "estado",
                    "etapa", "decision_eps", "gestor_nombre"):
            assert col in primera

    def test_filtro_eps(self, client, db_session):
        _seed(db_session, eps="SANITAS")
        _seed(db_session, eps="NUEVA EPS")
        r = client.get("/admin/glosas/exportar.csv?eps=SANITAS")
        body = r.text
        assert "SANITAS" in body
        assert "NUEVA EPS" not in body

    def test_filtro_estado(self, client, db_session):
        _seed(db_session, estado="RADICADA")
        _seed(db_session, estado="LEVANTADA")
        r = client.get("/admin/glosas/exportar.csv?estado=LEVANTADA")
        # 1 header + 1 data + posible empty line
        lineas = [l for l in r.text.strip().split("\n") if l]
        assert len(lineas) == 2  # header + 1 fila
