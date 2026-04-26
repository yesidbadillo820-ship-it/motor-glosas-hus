"""Tests del endpoint POST /admin/recalcular-dias-restantes (R91 P1)."""
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


def _seed(db, fecha_venc, dias_restantes, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_vencimiento=fecha_venc,
        dias_restantes=dias_restantes,
    ))
    db.commit()


class TestRecalcularDiasRestantes:
    def test_actualiza_glosas_desincronizadas(self, client, db_session):
        ahora = ahora_utc()
        # fecha_venc = +10 días + 1h (buffer para evitar precisión SQLite),
        # dias_restantes desactualizado a 99
        _seed(db_session, ahora + timedelta(days=10, hours=1),
              dias_restantes=99)
        # Otra: fecha_venc = -5 días + 1h, dias_restantes desactualizado a 0
        _seed(db_session, ahora + timedelta(days=-5, hours=1),
              dias_restantes=0)

        r = client.post("/admin/recalcular-dias-restantes")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["actualizadas"] == 2
        assert d["dry_run"] is False

        # Verificar persistencia
        glosas = db_session.query(GlosaRecord).all()
        valores = sorted(g.dias_restantes for g in glosas)
        # ~10 y ~-5 (puede haber ±1 por precisión SQLite)
        assert valores[0] in (-5, -6)
        assert valores[1] == 10

    def test_dry_run_no_modifica(self, client, db_session):
        _seed(db_session, ahora_utc() + timedelta(days=10),
              dias_restantes=99)
        r = client.post("/admin/recalcular-dias-restantes?dry_run=true")
        d = r.json()
        assert d["actualizadas"] == 1
        assert d["dry_run"] is True
        # BD intacta
        g = db_session.query(GlosaRecord).first()
        assert g.dias_restantes == 99

    def test_cerradas_se_ignoran(self, client, db_session):
        ahora = ahora_utc()
        _seed(db_session, ahora + timedelta(days=10),
              dias_restantes=999, estado="ACEPTADA")
        _seed(db_session, ahora + timedelta(days=10),
              dias_restantes=999, estado="LEVANTADA")
        r = client.post("/admin/recalcular-dias-restantes")
        d = r.json()
        assert d["actualizadas"] == 0
        assert d["cerradas_ignoradas"] == 2
        # Las dias_restantes quedan en 999 (no se tocan)
        for g in db_session.query(GlosaRecord).all():
            assert g.dias_restantes == 999

    def test_sin_cambios_no_cuenta_como_actualizada(self, client, db_session):
        ahora = ahora_utc()
        # fecha_venc = +10, pero como (vencimiento - ahora).days a veces da 9
        # por la fracción del día, mejor poner +10 días + 1h para garantizar 10
        _seed(db_session, ahora + timedelta(days=10, hours=1),
              dias_restantes=10)
        r = client.post("/admin/recalcular-dias-restantes")
        d = r.json()
        assert d["actualizadas"] == 0
        assert d["sin_cambios"] == 1
