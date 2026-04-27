"""Tests del checklist de tareas diarias del gestor."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import UsuarioRecord


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


@pytest.fixture
def otro_auditor():
    return UsuarioRecord(
        id=2, email="bob@hus.com", nombre="Bob",
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


class TestCRUD:
    def test_crear_default_hoy(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/usuarios/yo/tareas", json={
                "titulo": "Responder GLS-2024-00001",
            })
            assert r.status_code == 201
            d = r.json()
            assert d["fecha_para"] == date.today().isoformat()
            assert d["completada"] is False
            assert d["prioridad"] == "MEDIA"
        _clear()

    def test_crear_con_prioridad_y_glosa(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/usuarios/yo/tareas", json={
                "titulo": "Preparar informe semanal",
                "descripcion": "Resumen para coordinación",
                "prioridad": "ALTA",
                "glosa_id": 99,
            })
            assert r.status_code == 201
            d = r.json()
            assert d["prioridad"] == "ALTA"
            assert d["glosa_id"] == 99
            assert d["descripcion"] == "Resumen para coordinación"
        _clear()

    def test_prioridad_invalida_400(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/usuarios/yo/tareas", json={
                "titulo": "Test",
                "prioridad": "URGENTE",
            })
            assert r.status_code == 400
        _clear()

    def test_fecha_invalida_400(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/usuarios/yo/tareas", json={
                "titulo": "Test",
                "fecha_para": "no-es-fecha",
            })
            assert r.status_code == 400
        _clear()


class TestListado:
    def test_listar_solo_propias(self, db_session, auditor, otro_auditor):
        with _client(db_session, auditor) as c:
            c.post("/usuarios/yo/tareas", json={"titulo": "T-alice"})
        _clear()
        with _client(db_session, otro_auditor) as c:
            c.post("/usuarios/yo/tareas", json={"titulo": "T-bob"})
            r = c.get("/usuarios/yo/tareas")
            d = r.json()
            assert d["total"] == 1
            assert d["items"][0]["titulo"] == "T-bob"
        _clear()

    def test_filtrar_por_fecha(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            c.post("/usuarios/yo/tareas", json={
                "titulo": "Mañana",
                "fecha_para": "2099-12-31",
            })
            c.post("/usuarios/yo/tareas", json={"titulo": "Hoy"})
            r1 = c.get("/usuarios/yo/tareas")  # default hoy
            assert r1.json()["total"] == 1
            assert r1.json()["items"][0]["titulo"] == "Hoy"
            r2 = c.get("/usuarios/yo/tareas?fecha=2099-12-31")
            assert r2.json()["total"] == 1
            assert r2.json()["items"][0]["titulo"] == "Mañana"
        _clear()

    def test_resumen_solo_hoy(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            c.post("/usuarios/yo/tareas", json={"titulo": "Hoy 1"})
            c.post("/usuarios/yo/tareas", json={"titulo": "Hoy 2"})
            c.post("/usuarios/yo/tareas", json={
                "titulo": "Mañana", "fecha_para": "2099-12-31",
            })
            r = c.get("/usuarios/yo/tareas/resumen")
            d = r.json()
            assert d["total"] == 2
            assert d["pendientes"] == 2
            assert d["completadas"] == 0
        _clear()

    def test_excluir_completadas(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/usuarios/yo/tareas", json={"titulo": "Tarea X"})
            tid = r.json()["id"]
            c.patch(
                f"/usuarios/yo/tareas/{tid}", json={"completada": True},
            )
            c.post("/usuarios/yo/tareas", json={"titulo": "Pendiente"})
            r2 = c.get("/usuarios/yo/tareas?incluir_completadas=false")
            assert r2.json()["total"] == 1
            assert r2.json()["items"][0]["titulo"] == "Pendiente"
        _clear()


class TestPatch:
    def test_marcar_completada(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/usuarios/yo/tareas", json={"titulo": "Test"})
            tid = r.json()["id"]
            r2 = c.patch(
                f"/usuarios/yo/tareas/{tid}", json={"completada": True},
            )
            assert r2.status_code == 200
            d = r2.json()
            assert d["completada"] is True
            assert d["completada_en"] is not None
        _clear()

    def test_desmarcar_borra_completada_en(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/usuarios/yo/tareas", json={"titulo": "Test"})
            tid = r.json()["id"]
            c.patch(
                f"/usuarios/yo/tareas/{tid}", json={"completada": True},
            )
            r2 = c.patch(
                f"/usuarios/yo/tareas/{tid}", json={"completada": False},
            )
            d = r2.json()
            assert d["completada"] is False
            assert d["completada_en"] is None
        _clear()

    def test_editar_titulo_y_prioridad(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/usuarios/yo/tareas", json={"titulo": "Original"})
            tid = r.json()["id"]
            r2 = c.patch(f"/usuarios/yo/tareas/{tid}", json={
                "titulo": "Editado", "prioridad": "ALTA",
            })
            d = r2.json()
            assert d["titulo"] == "Editado"
            assert d["prioridad"] == "ALTA"
        _clear()

    def test_404_si_no_es_propia(
        self, db_session, auditor, otro_auditor,
    ):
        with _client(db_session, auditor) as c:
            r = c.post("/usuarios/yo/tareas", json={"titulo": "Tarea X"})
            tid = r.json()["id"]
        _clear()
        with _client(db_session, otro_auditor) as c:
            r2 = c.patch(
                f"/usuarios/yo/tareas/{tid}", json={"completada": True},
            )
            assert r2.status_code == 404
        _clear()


class TestDelete:
    def test_eliminar_propia(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/usuarios/yo/tareas", json={"titulo": "Tarea X"})
            tid = r.json()["id"]
            r2 = c.delete(f"/usuarios/yo/tareas/{tid}")
            assert r2.status_code == 204
            r3 = c.get("/usuarios/yo/tareas")
            assert r3.json()["total"] == 0
        _clear()

    def test_404_si_no_existe(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.delete("/usuarios/yo/tareas/9999")
            assert r.status_code == 404
        _clear()
