"""Tests del endpoint GET /admin/alertas-inteligentes (R121 P1)."""
from __future__ import annotations

from datetime import timedelta

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
        gestor_nombre="Alice",
        dictamen="<p>" + "x" * 100 + "</p>",
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestAlertasInteligentes:
    def test_estructura(self, client):
        r = client.get("/admin/alertas-inteligentes")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("generado_en", "total_alertas", "por_tipo", "items"):
            assert key in d
        for tipo in ("CRITICAL", "WARNING", "INFO", "BUSINESS"):
            assert tipo in d["por_tipo"]

    def test_sin_problemas_sin_alertas_criticas(self, client, db_session):
        # Glosa antigua (>7d) para evitar alerta INFO de "EPS nueva"
        _seed(db_session, dias_restantes=20,
              creado_en=ahora_utc() - timedelta(days=30))
        r = client.get("/admin/alertas-inteligentes")
        d = r.json()
        # No debe haber CRITICAL ni WARNING — solo posible INFO/BUSINESS
        assert d["por_tipo"]["CRITICAL"] == 0
        assert d["por_tipo"]["WARNING"] == 0

    def test_critical_muy_vencidas(self, client, db_session):
        _seed(db_session, dias_restantes=-50)
        r = client.get("/admin/alertas-inteligentes")
        d = r.json()
        criticas = [a for a in d["items"] if a["tipo"] == "CRITICAL"]
        assert len(criticas) == 1
        assert criticas[0]["count"] == 1
        assert "30 días" in criticas[0]["titulo"]

    def test_warning_muchas_criticas(self, client, db_session):
        # 5 glosas críticas → dispara WARNING
        for _ in range(5):
            _seed(db_session, dias_restantes=2)
        r = client.get("/admin/alertas-inteligentes")
        d = r.json()
        warnings = [a for a in d["items"]
                    if a["tipo"] == "WARNING" and a["categoria"] == "SLA"]
        assert len(warnings) == 1

    def test_warning_sin_gestor_threshold(self, client, db_session):
        # 4 sin gestor → NO dispara (threshold = 10)
        for _ in range(4):
            _seed(db_session, dias_restantes=20, gestor_nombre=None)
        r1 = client.get("/admin/alertas-inteligentes")
        d1 = r1.json()
        sin_gestor = [a for a in d1["items"]
                      if a["categoria"] == "ASIGNACION"]
        assert sin_gestor == []

        # Ahora 10 → SÍ dispara
        for _ in range(6):
            _seed(db_session, dias_restantes=20, gestor_nombre=None)
        r2 = client.get("/admin/alertas-inteligentes")
        d2 = r2.json()
        sin_gestor = [a for a in d2["items"]
                      if a["categoria"] == "ASIGNACION"]
        assert len(sin_gestor) == 1
        assert sin_gestor[0]["count"] == 10

    def test_business_alto_valor_sin_gestor(self, client, db_session):
        _seed(db_session, dias_restantes=20, gestor_nombre=None,
              valor_objetado=10_000_000)
        r = client.get("/admin/alertas-inteligentes")
        d = r.json()
        biz = [a for a in d["items"] if a["tipo"] == "BUSINESS"]
        assert len(biz) == 1
        assert biz[0]["count"] == 1
