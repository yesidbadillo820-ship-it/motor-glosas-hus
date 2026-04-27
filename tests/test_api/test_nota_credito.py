"""Tests del endpoint de nota crédito (glosas aceptadas)."""
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
def auditor():
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice",
        rol="AUDITOR", activo=1,
    )


def _client(db_session, user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: user
    return TestClient(app)


def _clear():
    from app.main import app
    app.dependency_overrides.clear()


def _seed(db, *, valor_objetado=200000, valor_aceptado=0.0):
    g = GlosaRecord(
        eps="DISPENSARIO MEDICO", paciente="X",
        codigo_glosa="TA0201", valor_objetado=valor_objetado,
        valor_aceptado=valor_aceptado, etapa="INICIAL",
        estado="RESPONDIDA", creado_en=ahora_utc(),
        factura="HUS493179",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g.id


class TestGuardar:
    def test_glosa_inexistente_404(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.patch(
                "/glosas/9999/nota-credito",
                json={"numero_nota": "NC-123"},
            )
            assert r.status_code == 404
        _clear()

    def test_sin_valor_aceptado_400(self, db_session, auditor):
        gid = _seed(db_session, valor_aceptado=0.0)
        with _client(db_session, auditor) as c:
            r = c.patch(
                f"/glosas/{gid}/nota-credito",
                json={"numero_nota": "NC-123"},
            )
            assert r.status_code == 400
        _clear()

    def test_aceptacion_parcial_guarda_nota(self, db_session, auditor):
        gid = _seed(db_session, valor_aceptado=16107.0)
        with _client(db_session, auditor) as c:
            r = c.patch(
                f"/glosas/{gid}/nota-credito",
                json={
                    "numero_nota": "NC-2026-0042",
                    "fecha_nota": "2026-04-27",
                    "observacion": "Acepta excedente facturado",
                },
            )
            assert r.status_code == 200
            d = r.json()
            assert d["numero_nota_credito"] == "NC-2026-0042"
            assert d["valor_nota_credito"] == 16107.0  # default = aceptado
            assert "Acepta excedente" in d["observacion"]
            assert d["fecha_nota_credito"] is not None
        _clear()

    def test_valor_explicito_pisa_default(self, db_session, auditor):
        gid = _seed(db_session, valor_aceptado=16107.0)
        with _client(db_session, auditor) as c:
            r = c.patch(
                f"/glosas/{gid}/nota-credito",
                json={"numero_nota": "NC-1", "valor": 20000.0},
            )
            assert r.status_code == 200
            assert r.json()["valor_nota_credito"] == 20000.0
        _clear()

    def test_fecha_invalida_400(self, db_session, auditor):
        gid = _seed(db_session, valor_aceptado=100.0)
        with _client(db_session, auditor) as c:
            r = c.patch(
                f"/glosas/{gid}/nota-credito",
                json={"numero_nota": "NC-1", "fecha_nota": "no-fecha"},
            )
            assert r.status_code == 400
        _clear()

    def test_numero_vacio_422(self, db_session, auditor):
        gid = _seed(db_session, valor_aceptado=100.0)
        with _client(db_session, auditor) as c:
            r = c.patch(
                f"/glosas/{gid}/nota-credito",
                json={"numero_nota": ""},
            )
            assert r.status_code == 422
        _clear()


class TestConsultar:
    def test_get_devuelve_la_nota(self, db_session, auditor):
        gid = _seed(db_session, valor_aceptado=500.0)
        with _client(db_session, auditor) as c:
            c.patch(
                f"/glosas/{gid}/nota-credito",
                json={"numero_nota": "NC-X"},
            )
            r = c.get(f"/glosas/{gid}/nota-credito")
            assert r.status_code == 200
            assert r.json()["numero_nota_credito"] == "NC-X"
        _clear()

    def test_get_sin_nota_devuelve_null(self, db_session, auditor):
        gid = _seed(db_session, valor_aceptado=500.0)
        with _client(db_session, auditor) as c:
            r = c.get(f"/glosas/{gid}/nota-credito")
            assert r.status_code == 200
            assert r.json()["numero_nota_credito"] is None
        _clear()


class TestBorrar:
    def test_delete_limpia_los_campos(self, db_session, auditor):
        gid = _seed(db_session, valor_aceptado=500.0)
        with _client(db_session, auditor) as c:
            c.patch(
                f"/glosas/{gid}/nota-credito",
                json={"numero_nota": "NC-Y"},
            )
            r = c.delete(f"/glosas/{gid}/nota-credito")
            assert r.status_code == 204
            r2 = c.get(f"/glosas/{gid}/nota-credito")
            assert r2.json()["numero_nota_credito"] is None
        _clear()
