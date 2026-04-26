"""Tests del endpoint POST /admin/ai-cache/limpiar (R86 P2)."""
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
from app.models.db import AICacheRecord, UsuarioRecord


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


def _seed(db, clave, dias_atras, respuesta="r" * 100):
    db.add(AICacheRecord(
        clave=clave, modelo="x", respuesta=respuesta,
        hit_count=0, creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestAiCacheLimpiar:
    def test_dry_run_no_borra(self, client, db_session):
        _seed(db_session, clave="a" * 64, dias_atras=60)
        _seed(db_session, clave="b" * 64, dias_atras=45)
        _seed(db_session, clave="c" * 64, dias_atras=10)

        r = client.post("/admin/ai-cache/limpiar?dry_run=true")
        assert r.status_code == 200, r.text
        d = r.json()
        # 2 entradas tienen >30 días → obsoletas, pero NO purgadas
        assert d["obsoletas"] == 2
        assert d["purgadas"] == 0
        assert d["dry_run"] is True
        # BD intacta
        assert db_session.query(AICacheRecord).count() == 3

    def test_purga_real_elimina_obsoletas(self, client, db_session):
        _seed(db_session, clave="a" * 64, dias_atras=60)
        _seed(db_session, clave="b" * 64, dias_atras=45)
        _seed(db_session, clave="c" * 64, dias_atras=10)

        r = client.post("/admin/ai-cache/limpiar")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["obsoletas"] == 2
        assert d["purgadas"] == 2
        assert d["dry_run"] is False
        # Solo queda la reciente
        restantes = db_session.query(AICacheRecord).count()
        assert restantes == 1

    def test_dias_custom_threshold_agresivo(self, client, db_session):
        """Con dias=7, todas las entradas >7 días son obsoletas."""
        _seed(db_session, clave="a" * 64, dias_atras=60)
        _seed(db_session, clave="b" * 64, dias_atras=10)
        _seed(db_session, clave="c" * 64, dias_atras=3)

        r = client.post("/admin/ai-cache/limpiar?dias=7")
        d = r.json()
        # 2 entradas tienen >7 días
        assert d["obsoletas"] == 2
        assert d["purgadas"] == 2
        assert d["dias_corte"] == 7
        assert db_session.query(AICacheRecord).count() == 1

    def test_default_dias_30(self, client, db_session):
        """Sin parámetros, usa default 30 días."""
        _seed(db_session, clave="a" * 64, dias_atras=20)

        r = client.post("/admin/ai-cache/limpiar")
        d = r.json()
        # 20 días < 30 → no obsoleta
        assert d["obsoletas"] == 0
        assert d["dias_corte"] == 30

    def test_reporta_espacio_liberado(self, client, db_session):
        _seed(db_session, clave="a" * 64, dias_atras=60, respuesta="x" * 500)
        _seed(db_session, clave="b" * 64, dias_atras=45, respuesta="x" * 300)

        r = client.post("/admin/ai-cache/limpiar")
        d = r.json()
        assert d["espacio_caracteres_liberado"] == 800
