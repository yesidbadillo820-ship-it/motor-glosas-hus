"""Tests del endpoint GET /papelera/stats (R128 P2)."""
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
from app.models.db import GlosaEliminadaRecord, UsuarioRecord


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
def usuario_coord(db_session):
    u = UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, usuario, dias_atras=1):
    db.add(GlosaEliminadaRecord(
        glosa_id_original=1, snapshot_json="{}",
        eliminado_por=usuario,
        eliminado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestPapeleraStats:
    def test_estructura(self, client):
        r = client.get("/papelera/stats")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_papelera", "eliminadas_ultimas_24h",
                    "eliminadas_ultimos_7d", "eliminadas_ultimos_30d",
                    "proximas_a_expirar", "top_5_eliminadores"):
            assert key in d

    def test_clasifica_por_ventana(self, client, db_session):
        _seed(db_session, "alice@x", dias_atras=0)   # 24h
        _seed(db_session, "alice@x", dias_atras=5)   # 7d
        _seed(db_session, "alice@x", dias_atras=20)  # 30d
        _seed(db_session, "alice@x", dias_atras=40)  # fuera

        r = client.get("/papelera/stats")
        d = r.json()
        assert d["total_papelera"] == 4
        assert d["eliminadas_ultimas_24h"] == 1
        assert d["eliminadas_ultimos_7d"] == 2
        assert d["eliminadas_ultimos_30d"] == 3

    def test_top_5_eliminadores(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "alice@x")
        for _ in range(2):
            _seed(db_session, "bob@x")
        _seed(db_session, "carol@x")

        r = client.get("/papelera/stats")
        d = r.json()
        top = d["top_5_eliminadores"]
        assert top[0] == {"usuario": "alice@x", "eliminadas": 5}
        assert top[1] == {"usuario": "bob@x", "eliminadas": 2}
        assert top[2] == {"usuario": "carol@x", "eliminadas": 1}

    def test_proximas_a_expirar(self, client, db_session):
        # Hace 25 días → próxima a expirar (≤7d para corte 30d)
        _seed(db_session, "u@x", dias_atras=25)
        # Hace 10 días → no próxima
        _seed(db_session, "u@x", dias_atras=10)
        r = client.get("/papelera/stats")
        d = r.json()
        assert d["proximas_a_expirar"] == 1
