"""El expediente guarda constancia de la verificación contractual.

La regla de construcción es que nada está terminado si no queda en el
expediente. Analizar una glosa ya resuelve el contrato por la fecha del
hecho; estos tests garantizan lo que faltaba: que esa decisión quede
REGISTRADA (audit log) y sea CONSULTABLE (línea de tiempo de la glosa),
con los tres veredictos posibles:

  - VIGENTE                → había contrato ese día (queda número y factor)
  - SIN_CONTRATO_VIGENTE   → el pagador existe en la malla pero ese día
                             no lo cubría ningún contrato
  - PAGADOR_FUERA_DE_MALLA → el pagador ni aparece en la malla

Mismo andamiaje que test_analizar_e2e: service IA mockeado, SQLite en
memoria, usuario fake. Nada de red.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models.db import AuditLogRecord, UsuarioRecord
from app.models.schemas import GlosaResult

TABLA = "TA0201 — Diferencia tarifa CUPS 890750 valor objetado $168.563 según contrato vigente."


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


@pytest.fixture
def usuario_fake():
    return UsuarioRecord(
        id=1,
        email="auditor@hus.gov.co",
        nombre="Auditor Test",
        rol="AUDITOR",
        activo=1,
    )


@pytest.fixture
def service_mock():
    svc = MagicMock()
    svc.analizar = AsyncMock(
        return_value=GlosaResult(
            tipo="RESPUESTA RE9901",
            resumen="Defensa técnica generada",
            dictamen="<div>Dictamen mock</div>",
            codigo_glosa="TA0201",
            valor_objetado="$ 168,563",
            paciente="N/A",
            mensaje_tiempo="EN TÉRMINOS",
            color_tiempo="green",
            score=85.0,
            dias_restantes=10,
            modelo_ia="mock/test",
        )
    )
    return svc


@pytest.fixture
def client(db_session, usuario_fake, service_mock):
    from app.api.deps import get_usuario_actual
    from app.api.routers.analizar import get_glosa_service
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_fake
    app.dependency_overrides[get_glosa_service] = lambda: service_mock

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def _analizar(client, eps: str, fecha: str | None = None) -> int:
    datos = {
        "eps": eps,
        "etapa": "RESPUESTA",
        "valor_aceptado": "0",
        "tabla_excel": TABLA,
    }
    if fecha:
        datos["fecha_radicacion"] = fecha
    resp = client.post("/analizar", data=datos)
    assert resp.status_code == 200, resp.text
    glosa_id = resp.json()["glosa_id"]
    assert glosa_id is not None
    return glosa_id


def _constancia(db_session, glosa_id: int) -> AuditLogRecord:
    filas = (
        db_session.query(AuditLogRecord)
        .filter(
            AuditLogRecord.accion == "VERIFICACION_CONTRACTUAL",
            AuditLogRecord.tabla == "historial",
            AuditLogRecord.registro_id == glosa_id,
        )
        .all()
    )
    assert len(filas) == 1, "cada análisis deja exactamente una constancia contractual"
    return filas[0]


class TestConstanciaEnExpediente:
    def test_contrato_vigente_queda_con_numero_y_factor(self, client, db_session):
        """Una atención de sep-2025 de COMPENSAR se defendió con el
        CSS009-2024 al 0.85 — y el expediente lo dice, no hay que
        reconstruirlo de memoria cuando la EPS discuta la tarifa."""
        glosa_id = _analizar(client, "COMPENSAR", fecha="2025-09-15")
        fila = _constancia(db_session, glosa_id)

        assert fila.campo == "VIGENTE"
        assert "CSS009-2024" in (fila.valor_nuevo or "")
        assert fila.usuario_email == "auditor@hus.gov.co"

        detalle = json.loads(fila.detalle)
        assert detalle["veredicto"] == "VIGENTE"
        assert detalle["fecha_hecho"] == "2025-09-15"
        assert detalle["fecha_es_del_formulario"] is True
        assert detalle["contrato"]["factor"] == pytest.approx(0.85)

    def test_dia_sin_contrato_queda_declarado(self, client, db_session):
        """El CSS009-2024 venció el 3 de abril de 2026: un hecho de julio
        no tiene contrato y esa alerta debe quedar escrita en el
        expediente, no solo en el prompt que ya nadie vuelve a leer."""
        glosa_id = _analizar(client, "COMPENSAR", fecha="2026-07-20")
        fila = _constancia(db_session, glosa_id)

        assert fila.campo == "SIN_CONTRATO_VIGENTE"
        assert fila.valor_nuevo == "SIN_CONTRATO_VIGENTE"

        detalle = json.loads(fila.detalle)
        assert detalle["veredicto"] == "SIN_CONTRATO_VIGENTE"
        assert detalle["contrato"] is None
        assert "2026-07-20" in detalle["resumen"]

    def test_pagador_desconocido_queda_declarado(self, client, db_session):
        """Si el pagador ni figura en la malla, el expediente lo dice tal
        cual: es la señal para que contratación revise, no un silencio."""
        glosa_id = _analizar(client, "ASEGURADORA FANTASMA DEL NORTE")
        fila = _constancia(db_session, glosa_id)

        assert fila.campo == "PAGADOR_FUERA_DE_MALLA"
        detalle = json.loads(fila.detalle)
        assert detalle["veredicto"] == "PAGADOR_FUERA_DE_MALLA"
        assert detalle["contrato"] is None

    def test_sin_fecha_se_verifica_con_hoy_y_se_declara(self, client, db_session):
        """Cuando el formulario no trae fecha se verifica con la de hoy,
        pero el expediente deja claro que la fecha NO vino del formulario:
        un auditor que revise luego sabe que debe confirmarla."""
        glosa_id = _analizar(client, "COMPENSAR")
        fila = _constancia(db_session, glosa_id)

        detalle = json.loads(fila.detalle)
        assert detalle["fecha_es_del_formulario"] is False
        assert detalle["malla_al"]  # de qué corte de malla salió el veredicto

    def test_la_linea_de_tiempo_lo_muestra(self, client, db_session):
        """La constancia no es una fila perdida en una tabla: aparece en
        GET /glosas/{id}/timeline junto a versiones y cambios de estado,
        que es donde el auditor reconstruye la historia de la glosa."""
        glosa_id = _analizar(client, "COMPENSAR", fecha="2025-09-15")

        resp = client.get(f"/glosas/{glosa_id}/timeline")
        assert resp.status_code == 200, resp.text
        lista = resp.json()["eventos"]

        verificaciones = [e for e in lista if e["tipo"] == "AUDIT_VERIFICACION_CONTRACTUAL"]
        assert len(verificaciones) == 1
        ev = verificaciones[0]
        assert ev["metadata"]["campo"] == "VIGENTE"
        assert "CSS009-2024" in ev["metadata"]["valor_nuevo"]

        # El detalle visible es la frase en cristiano, no el JSON crudo:
        # eso es lo que lee el auditor en la línea de tiempo.
        assert ev["detalle"].startswith("Contrato CSS009-2024 vigente")
        assert not ev["detalle"].lstrip().startswith("{")
        # Y el dato completo sigue disponible para quien lo necesite.
        assert ev["metadata"]["constancia"]["veredicto"] == "VIGENTE"
        assert ev["metadata"]["constancia"]["contrato"]["factor"] == pytest.approx(0.85)

    def test_un_fallo_en_la_malla_no_tumba_el_analisis(self, client, db_session, monkeypatch):
        """La constancia es un extra de trazabilidad: si la malla revienta,
        el análisis (que ya costó tokens y tiempo del auditor) sale igual."""
        from app.services import malla_contractual

        def _explota(*a, **k):
            raise RuntimeError("malla rota a propósito")

        monkeypatch.setattr(malla_contractual, "vigente", _explota)

        glosa_id = _analizar(client, "COMPENSAR", fecha="2025-09-15")
        assert glosa_id is not None  # el análisis respondió 200 igual

        filas = (
            db_session.query(AuditLogRecord)
            .filter(AuditLogRecord.accion == "VERIFICACION_CONTRACTUAL")
            .all()
        )
        assert filas == []  # sin constancia, pero sin tumbar nada
