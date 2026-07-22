"""Tests del endpoint GET /glosas/stats/heatmap-actividad (R89 P1)."""

from __future__ import annotations

from datetime import timedelta

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


def _seed(db, creado):
    db.add(
        GlosaRecord(
            eps="X",
            paciente="X",
            codigo_glosa="TA0201",
            valor_objetado=100,
            etapa="X",
            estado="RADICADA",
            creado_en=creado,
        )
    )
    db.commit()


def _fecha_reciente(weekday, hora, minuto):
    """Fecha del `weekday` (0=Lunes) más reciente hace 7-13 días.

    El endpoint solo cuenta una ventana de 90 días; una fecha fija caduca
    cuando el calendario avanza (los tests pasaban y luego fallaban solos).
    """
    base = ahora_utc() - timedelta(days=7)
    base -= timedelta(days=(base.weekday() - weekday) % 7)
    return base.replace(hour=hora, minute=minuto, second=0, microsecond=0)


class TestHeatmapActividad:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/heatmap-actividad")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 0
        # Matriz 7×24 toda en cero
        assert len(d["matriz"]) == 7
        assert all(len(row) == 24 for row in d["matriz"])
        assert all(cell == 0 for row in d["matriz"] for cell in row)
        assert len(d["horas"]) == 24

    def test_estructura_matriz(self, client):
        r = client.get("/glosas/stats/heatmap-actividad")
        d = r.json()
        assert d["dias_semana"][0] == "Lunes"
        assert d["dias_semana"][6] == "Domingo"
        assert d["horas"] == list(range(24))

    def test_ubica_eventos_en_celda_correcta(self, client, db_session):
        # Lunes (weekday=0) 09:30 → fila 0, col 9
        _seed(db_session, _fecha_reciente(0, 9, 30))
        _seed(db_session, _fecha_reciente(0, 9, 45))
        # Miércoles (weekday=2) 14:15 → fila 2, col 14
        _seed(db_session, _fecha_reciente(2, 14, 15))

        r = client.get("/glosas/stats/heatmap-actividad")
        d = r.json()
        assert d["matriz"][0][9] == 2
        assert d["matriz"][2][14] == 1
        assert d["total"] == 3

    def test_excluye_fuera_de_ventana(self, client, db_session):
        # Hoy: dentro
        ahora = ahora_utc()
        db_session.add(
            GlosaRecord(
                eps="X",
                paciente="X",
                codigo_glosa="X",
                valor_objetado=100,
                etapa="X",
                estado="RADICADA",
                creado_en=ahora,
            )
        )
        # 200 días atrás: fuera con default (90)
        db_session.add(
            GlosaRecord(
                eps="X",
                paciente="X",
                codigo_glosa="X",
                valor_objetado=100,
                etapa="X",
                estado="RADICADA",
                creado_en=ahora - timedelta(days=200),
            )
        )
        db_session.commit()

        r = client.get("/glosas/stats/heatmap-actividad")
        d = r.json()
        assert d["total"] == 1
