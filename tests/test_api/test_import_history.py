"""Tests del endpoint GET /sistema/import-history (R149 P1)."""

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
def usuario_coord():
    return UsuarioRecord(
        id=1,
        email="coord@hus.gov.co",
        rol="COORDINADOR",
        activo=1,
    )


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, fecha):
    db.add(
        GlosaRecord(
            eps="X",
            paciente="X",
            codigo_glosa="C",
            valor_objetado=1000,
            etapa="X",
            estado="RADICADA",
            creado_en=fecha,
        )
    )
    db.commit()


class TestImportHistory:
    def test_estructura(self, client):
        r = client.get("/sistema/import-history")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "umbral_cluster", "total_clusters_detectados", "items"):
            assert key in d
        assert d["umbral_cluster"] == 10

    def test_pocas_glosas_no_genera_cluster(self, client, db_session):
        for _ in range(5):
            _seed(db_session, ahora_utc())
        r = client.get("/sistema/import-history")
        d = r.json()
        # 5 < 10 → no cluster
        assert d["items"] == []

    def test_cluster_detectado(self, client, db_session):
        # 12 glosas en la misma hora (hace 3 días)
        from datetime import timedelta

        ts = ahora_utc() - timedelta(days=3)
        for _ in range(12):
            _seed(db_session, ts)
        r = client.get("/sistema/import-history")
        d = r.json()
        assert d["total_clusters_detectados"] == 1
        assert d["items"][0]["glosas_creadas"] == 12

    def test_orden_clusters_desc(self, client, db_session):
        # Antes se hardcodeaban fechas absolutas (2026-04-10 / 2026-04-12) y
        # la consulta usaba ?dias=60. Con el paso del tiempo, abril 2026 cae
        # FUERA de la ventana de 60 días → el cluster de 20 desaparece y el
        # test falla con "11 != 20". Anclamos a relativo a hoy.
        from datetime import timedelta

        ts1 = ahora_utc() - timedelta(days=10, hours=4)  # cluster grande
        ts2 = ahora_utc() - timedelta(days=8, hours=2)  # cluster pequeño, más reciente
        for _ in range(20):
            _seed(db_session, ts1)
        for _ in range(11):
            _seed(db_session, ts2)
        r = client.get("/sistema/import-history?dias=60")
        d = r.json()
        # Orden por cantidad descendente: primero el de 20, luego el de 11.
        assert d["items"][0]["glosas_creadas"] == 20
        assert d["items"][1]["glosas_creadas"] == 11
