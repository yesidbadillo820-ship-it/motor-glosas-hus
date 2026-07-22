"""Tests de los endpoints /lotes y /agente/lotes (Fase 1 app unificada)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.database import Base, get_db
from app.models.db import UsuarioRecord
from tests.test_services.test_lotes_service import excel_bytes

TOKEN = "token-de-prueba-agente"


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
def client(db_session, usuario, monkeypatch):
    from app.api.deps import get_usuario_actual
    from app.main import app

    monkeypatch.setenv("AGENTE_LOTES_TOKEN", TOKEN)
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def subir_lote(client, **data):
    payload = {"pagador": "COOSALUD", "hoja": "BASE", "incluir_calidad": "false"}
    payload.update(data)
    return client.post(
        "/lotes/",
        files={"archivo": ("lote.xlsx", excel_bytes(), "application/octet-stream")},
        data=payload,
    )


def test_subir_listar_y_detalle(client):
    r = subir_lote(client)
    assert r.status_code == 201, r.text
    lote = r.json()
    assert lote["estado"] == "EN_COLA"
    assert lote["total_facturas"] == 2
    assert lote["total_glosas"] == 4

    r = client.get("/lotes/")
    assert r.status_code == 200
    assert [lo["id"] for lo in r.json()] == [lote["id"]]

    r = client.get(f"/lotes/{lote['id']}")
    assert r.status_code == 200
    detalle = r.json()
    assert {f["factura"] for f in detalle["facturas"]} == {"HUS100", "HUS200"}
    assert detalle["tareas"][0]["estado"] == "PENDIENTE"


def test_subir_extension_invalida(client):
    r = client.post(
        "/lotes/",
        files={"archivo": ("lote.pdf", b"x", "application/pdf")},
        data={"pagador": "COOSALUD"},
    )
    assert r.status_code == 400


def test_subir_pagador_no_soportado(client):
    r = subir_lote(client, pagador="SIMED")
    assert r.status_code == 400
    assert "no soportado" in r.json()["detail"]


def test_agente_requiere_token(client):
    r = client.post("/agente/lotes/tareas/reclamar", json={"agente": "pc"})
    assert r.status_code == 401
    r = client.post(
        "/agente/lotes/tareas/reclamar",
        json={"agente": "pc"},
        headers={"X-Agente-Token": "otro"},
    )
    assert r.status_code == 401


def test_agente_deshabilitado_sin_token_configurado(client, monkeypatch):
    monkeypatch.delenv("AGENTE_LOTES_TOKEN")
    get_settings.cache_clear()
    r = client.post(
        "/agente/lotes/tareas/reclamar",
        json={"agente": "pc"},
        headers={"X-Agente-Token": TOKEN},
    )
    assert r.status_code == 503


def test_flujo_completo_del_agente(client):
    lote_id = subir_lote(client).json()["id"]
    headers = {"X-Agente-Token": TOKEN}

    # Sin reclamar, el excel de una tarea inexistente es 404
    assert client.get("/agente/lotes/tareas/999/excel", headers=headers).status_code == 404

    r = client.post("/agente/lotes/tareas/reclamar", json={"agente": "pc-cartera"}, headers=headers)
    assert r.status_code == 200
    tarea = r.json()
    assert tarea["lote_id"] == lote_id
    assert tarea["tipo"] == "RESPONDER_COOSALUD"
    assert tarea["hoja"] == "BASE"

    # Segunda reclamación: no hay más tareas
    r = client.post("/agente/lotes/tareas/reclamar", json={"agente": "pc2"}, headers=headers)
    assert r.status_code == 204

    # El Excel descargado es el original
    r = client.get(f"/agente/lotes/tareas/{tarea['tarea_id']}/excel", headers=headers)
    assert r.status_code == 200
    assert r.content == excel_bytes()

    # Progreso incremental → el semáforo avanza
    r = client.post(
        f"/agente/lotes/tareas/{tarea['tarea_id']}/progreso",
        json={"exito": True, "resultados": [{"factura": "HUS100", "estado": "OK"}]},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["aplicadas"] == 1
    detalle = client.get(f"/lotes/{lote_id}").json()
    estados = {f["factura"]: f["estado"] for f in detalle["facturas"]}
    assert estados == {"HUS100": "OK", "HUS200": "PENDIENTE"}
    assert detalle["estado"] == "EN_PROCESO"

    # Completar con una pendiente → COMPLETADO_CON_PENDIENTES
    r = client.post(
        f"/agente/lotes/tareas/{tarea['tarea_id']}/completar",
        json={
            "exito": True,
            "resultados": [
                {"factura": "HUS100", "estado": "OK"},
                {"factura": "HUS200", "estado": "PENDIENTE_PDX", "detalle": "falta PDX"},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "COMPLETADO_CON_PENDIENTES"
    assert r.json()["resumen"]["pendientes"] == 1

    # La tarea ya no está RECLAMADA: reportar de nuevo es 409
    r = client.post(
        f"/agente/lotes/tareas/{tarea['tarea_id']}/completar",
        json={"exito": True, "resultados": []},
        headers=headers,
    )
    assert r.status_code == 409


# ── Ronda 31: saneo del nombre de archivo (path traversal + header) ──────


def test_nombre_archivo_con_traversal_se_sanea(client):
    r = client.post(
        "/lotes/",
        files={
            "archivo": (
                r"..\..\..\Windows\System32\evil.xlsx",
                excel_bytes(),
                "application/octet-stream",
            )
        },
        data={"pagador": "COOSALUD", "hoja": "BASE", "incluir_calidad": "false"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["nombre_archivo"] == "evil.xlsx"


def test_nombre_archivo_solo_puntos_rechazado(client):
    r = client.post(
        "/lotes/",
        files={"archivo": (r"carpeta\..", excel_bytes(), "application/octet-stream")},
        data={"pagador": "COOSALUD", "hoja": "BASE", "incluir_calidad": "false"},
    )
    assert r.status_code == 400
