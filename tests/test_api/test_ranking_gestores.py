"""Tests del endpoint GET /admin/ranking-gestores (R148 P1)."""
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


def _seed(db, gestor, estado="LEVANTADA", dias_atras_dec=10):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        fecha_decision_eps=ahora_utc() - timedelta(days=dias_atras_dec),
    ))
    db.commit()


class TestRankingGestores:
    def test_estructura(self, client):
        r = client.get("/admin/ranking-gestores?min_glosas=1")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "min_glosas_filtro",
                    "total_gestores_evaluados", "items"):
            assert key in d

    def test_top_performer_5_estrellas(self, client, db_session):
        # Alice: 5 LEVANTADA / 5 → 100% → 5★ TOP_PERFORMER
        for _ in range(5):
            _seed(db_session, "Alice", "LEVANTADA")
        r = client.get("/admin/ranking-gestores?min_glosas=1")
        d = r.json()
        item = next(it for it in d["items"] if it["gestor"] == "Alice")
        assert item["rating"] == 5
        assert item["badge"] == "TOP_PERFORMER"
        assert item["position"] == 1

    def test_en_progreso_1_estrella(self, client, db_session):
        # Bob: 1 LEVANTADA / 5 → 20% → 2★ EN_PROGRESO
        _seed(db_session, "Bob", "LEVANTADA")
        for _ in range(4):
            _seed(db_session, "Bob", "ACEPTADA")
        r = client.get("/admin/ranking-gestores?min_glosas=1")
        d = r.json()
        item = next(it for it in d["items"] if it["gestor"] == "Bob")
        assert item["rating"] == 2
        assert item["badge"] == "EN_PROGRESO"

    def test_filtra_min_glosas(self, client, db_session):
        # Pequeño con solo 2 → no entra con min=3
        _seed(db_session, "Pequeño", "LEVANTADA")
        _seed(db_session, "Pequeño", "LEVANTADA")
        r = client.get("/admin/ranking-gestores?min_glosas=3")
        d = r.json()
        assert all(it["gestor"] != "Pequeño" for it in d["items"])

    def test_position_consecutiva(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "Alice", "LEVANTADA")
        for _ in range(5):
            _seed(db_session, "Bob", "ACEPTADA")
        r = client.get("/admin/ranking-gestores?min_glosas=1")
        d = r.json()
        positions = [it["position"] for it in d["items"]]
        assert positions == list(range(1, len(d["items"]) + 1))
