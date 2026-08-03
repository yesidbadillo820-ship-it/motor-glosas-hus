"""Constructor de Agentes: construir un agente es guardar una ficha.

El runner es el mismo del asistente maestro: la misión va como sistema
adicional y las herramientas se recortan a las permitidas. Estas pruebas
verifican el ciclo completo (construir → correr → retirar), que la lista
blanca de herramientas de verdad recorta, y que todo queda auditado.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models.db import AgenteRecord, AuditLogRecord, UsuarioRecord


@pytest.fixture
def db_session():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _cliente(db_session, rol="AUDITOR"):
    from app.api.deps import get_usuario_actual
    from app.main import app
    from app.services.rate_limit_ia import consumir_cupo_ia

    u = UsuarioRecord(id=1, email="auditor@hus.gov.co", nombre="A", rol=rol, activo=1)
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: u
    app.dependency_overrides[consumir_cupo_ia] = lambda: None
    return TestClient(app)


@pytest.fixture
def cliente(db_session):
    from app.main import app

    c = _cliente(db_session)
    with c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def cliente_viewer(db_session):
    from app.main import app

    c = _cliente(db_session, rol="VIEWER")
    with c:
        yield c
    app.dependency_overrides.clear()


FICHA = {
    "nombre": "Vigilante de prueba",
    "mision": "Vigilar los vencimientos de prueba y avisar qué responder primero.",
    "instrucciones": "Siempre empezar por lo rojo.",
    "herramientas": ["diagnostico_operacion", "consultar_expediente"],
}


class TestConstruir:
    def test_construir_lista_y_auditar(self, cliente, db_session):
        r = cliente.post("/agentes", json=FICHA)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["nombre"] == FICHA["nombre"]
        assert d["herramientas"] == FICHA["herramientas"]

        lista = cliente.get("/agentes").json()
        assert any(a["nombre"] == FICHA["nombre"] for a in lista["agentes"])
        assert "diagnostico_operacion" in lista["herramientas_disponibles"]
        assert len(lista["plantillas"]) >= 2

        assert (
            db_session.query(AuditLogRecord)
            .filter(AuditLogRecord.accion == "AGENTE_CREADO")
            .count()
            == 1
        )

    def test_herramienta_desconocida_se_rechaza(self, cliente):
        mala = {**FICHA, "herramientas": ["borrar_base_de_datos"]}
        r = cliente.post("/agentes", json=mala)
        assert r.status_code == 400
        assert "desconocidas" in r.json()["detail"].lower()

    def test_viewer_no_construye(self, cliente_viewer):
        assert cliente_viewer.post("/agentes", json=FICHA).status_code == 403


class TestCorrer:
    def test_corre_con_su_mision_y_solo_sus_herramientas(self, cliente, db_session, monkeypatch):
        """La ficha manda: el runner recibe la misión como sistema extra y
        la lista blanca exacta de herramientas."""
        capturado = {}

        async def _runner_fake(mensajes, db, current_user, **kw):
            capturado.update(kw)
            capturado["pregunta"] = mensajes[0]["content"]
            return {
                "respuesta": "Hecho: 2 glosas urgentes.",
                "tools_llamadas": [{"name": "diagnostico_operacion"}],
            }

        import app.api.routers.agentes  # noqa: F401 — asegura registro
        from app.services import asistente_maestro as am

        monkeypatch.setattr(am, "chat_con_asistente", _runner_fake)

        agente_id = cliente.post("/agentes", json=FICHA).json()["id"]
        r = cliente.post(f"/agentes/{agente_id}/correr", json={"pregunta": "¿Qué hago hoy?"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["agente"] == FICHA["nombre"]
        assert "urgentes" in d["respuesta"]

        assert FICHA["mision"] in capturado["system_extra"]
        assert "Siempre empezar por lo rojo." in capturado["system_extra"]
        assert capturado["tools_permitidas"] == FICHA["herramientas"]

        fila = (
            db_session.query(AuditLogRecord).filter(AuditLogRecord.accion == "AGENTE_CORRIDO").one()
        )
        assert json.loads(fila.detalle)["tools_usadas"] == ["diagnostico_operacion"]

    def test_agente_retirado_no_corre(self, cliente, db_session):
        agente_id = cliente.post("/agentes", json=FICHA).json()["id"]
        db_session.query(AgenteRecord).filter_by(id=agente_id).update({"activo": 0})
        db_session.commit()
        r = cliente.post(f"/agentes/{agente_id}/correr", json={"pregunta": "hola"})
        assert r.status_code == 404


class TestLaListaBlancaRecortaDeVerdad:
    async def test_el_runner_filtra_tools(self, monkeypatch):
        """Directo al runner: con lista blanca, a la API solo viajan esas."""
        import httpx

        from app.services import asistente_maestro as am

        enviado = {}

        class _Resp:
            status_code = 200

            def json(self):
                return {
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }

        class _Cliente:
            def __init__(self, *a, **k): ...
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers=None, json=None):
                enviado.update(json)
                return _Resp()

        monkeypatch.setattr(httpx, "AsyncClient", _Cliente)
        r = await am.chat_con_asistente(
            [{"role": "user", "content": "hola"}],
            db=None,
            current_user=None,
            api_key="sk-test",
            modelo="claude-test",
            system_extra="MISIÓN: probar.",
            tools_permitidas=["consultar_expediente"],
        )
        assert not r.get("error")
        assert [t["name"] for t in enviado["tools"]] == ["consultar_expediente"]
        assert "MISIÓN: probar." in enviado["system"]


class TestPantalla:
    def test_existe_el_constructor(self):
        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert 'id="p-agentes"' in html
        assert 'id="sn-agentes"' in html
        assert "function agCrear" in html
        assert "function agCorrer" in html
        assert "agPlantilla" in html  # plantillas de un clic
