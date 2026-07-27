"""Tests del endpoint GET /glosas/stats/heatmap-actividad (R89 P1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def _reciente_iso(dia_semana: int, hora: int, minuto: int) -> str:
    """ISO (UTC, naive) de un día reciente que cae en `dia_semana` (0=Lunes) a
    la hora dada. Relativo a hoy para NO caer fuera de la ventana de 90 días al
    avanzar el calendario (antes usaba fechas fijas de abril → time-bomb de CI)."""
    base = ahora_utc().replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    lunes = base - timedelta(days=base.weekday() + 7)  # lunes de la semana pasada
    return (lunes + timedelta(days=dia_semana)).replace(hour=hora, minute=minuto).isoformat(sep=" ")


def _seed(db, fecha_iso):
    """fecha_iso: '2026-04-20 09:00' (UTC)."""
    creado = datetime.fromisoformat(fecha_iso).replace(tzinfo=timezone.utc)
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
        # Lunes reciente (weekday=0). 09:30 → fila 0, col 9. Fechas relativas
        # para no salirse de la ventana de 90 días al pasar el calendario.
        _seed(db_session, _reciente_iso(0, 9, 30))
        _seed(db_session, _reciente_iso(0, 9, 45))
        # Miércoles reciente (weekday=2). 14:15 → fila 2, col 14
        _seed(db_session, _reciente_iso(2, 14, 15))

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
