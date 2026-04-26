"""Tests integration end-to-end del endpoint POST /analizar (R60 P1).

Estrategia: usar app.dependency_overrides para sustituir
  - get_usuario_actual → user fake (evita login real con JWT)
  - get_glosa_service → mock del service que devuelve GlosaResult fijo
  - get_db → sesión SQLite in-memory aislada del seed

Así se valida la cadena completa endpoint → repository → response sin
tocar Anthropic ni hacer JWT real.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models.db import UsuarioRecord
from app.models.schemas import GlosaResult


@pytest.fixture
def db_session():
    """SQLite in-memory aislada por test.

    Usa StaticPool para que TestClient (thread distinto) y el test
    (thread principal) compartan la misma conexión — sin esto SQLite
    lanza 'objects created in a thread can only be used in that same'.
    """
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
        id=1, email="auditor@hus.gov.co", nombre="Auditor Test",
        rol="AUDITOR", activo=1,
    )


@pytest.fixture
def service_mock():
    """Mock del GlosaService.analizar — devuelve un GlosaResult plausible."""
    svc = MagicMock()
    svc.analizar = AsyncMock(return_value=GlosaResult(
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
    ))
    return svc


@pytest.fixture
def client_con_overrides(db_session, usuario_fake, service_mock):
    """TestClient con TODAS las dependencias mockeadas para flujo E2E."""
    from app.api.deps import get_usuario_actual
    from app.api.routers.analizar import get_glosa_service
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_fake
    app.dependency_overrides[get_glosa_service] = lambda: service_mock

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


class TestAnalizarFlowE2E:
    def test_analizar_basico_persiste_glosa(self, client_con_overrides, db_session):
        """Flujo principal: POST /analizar con datos mínimos crea
        GlosaRecord en BD."""
        from app.models.db import GlosaRecord

        resp = client_con_overrides.post(
            "/analizar",
            data={
                "eps": "FAMISANAR",
                "etapa": "RESPUESTA",
                "valor_aceptado": "0",
                "tabla_excel": (
                    "TA0201 — Diferencia tarifa CUPS 890750 valor objetado "
                    "$168.563 según contrato vigente."
                ),
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Estructura esperada de GlosaResult
        assert "dictamen" in data
        assert data["codigo_glosa"] == "TA0201"
        # Estado RADICADA porque val_aceptado=0
        # Y debe haberse creado fila en GlosaRecord
        glosas = db_session.query(GlosaRecord).all()
        assert len(glosas) == 1
        assert glosas[0].eps == "FAMISANAR"
        assert glosas[0].codigo_glosa == "TA0201"

    def test_analizar_aceptacion_total_genera_RE9702(self, client_con_overrides, db_session):
        """Si val_aceptado >= val_objetado → estado ACEPTADA + RE9702."""
        from app.models.db import GlosaRecord

        resp = client_con_overrides.post(
            "/analizar",
            data={
                "eps": "FAMISANAR",
                "etapa": "RESPUESTA",
                "valor_aceptado": "168563",  # = valor objetado mock
                "tabla_excel": (
                    "TA0201 — Diferencia tarifa CUPS 890750 valor objetado $168.563"
                ),
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # tipo debería incluir RE9702 (aceptación total)
        assert "RE9702" in data["tipo"]
        # BD: estado ACEPTADA
        g = db_session.query(GlosaRecord).first()
        assert g.estado == "ACEPTADA"

    def test_analizar_input_invalido_devuelve_422(self, client_con_overrides):
        """Validación: tabla_excel demasiado corta debe rechazarse."""
        resp = client_con_overrides.post(
            "/analizar",
            data={
                "eps": "X",  # min_length=2 — ok pero corto
                "etapa": "Y",  # min_length=3 — falla
                "tabla_excel": "ab",  # min_length=3 — falla
            },
        )
        # FastAPI Form validation o GlosaInput validator atrapan
        assert resp.status_code in (400, 422)

    def test_analizar_modo_auditoria_previa(self, client_con_overrides, db_session):
        """REGRESIÓN R59: modo auditoria_previa debe procesar y persistir."""
        from app.models.db import GlosaRecord

        resp = client_con_overrides.post(
            "/analizar",
            data={
                "eps": "FAMISANAR",
                "etapa": "REVISION",
                "valor_aceptado": "0",
                "tabla_excel": "TA0201 — análisis preventivo de la glosa",
                "modo_respuesta": "auditoria_previa",
            },
        )
        assert resp.status_code == 200, resp.text
        # Glosa creada
        assert db_session.query(GlosaRecord).count() == 1

    def test_analizar_metricas_se_persisten(self, client_con_overrides, db_session):
        """Verifica que cada glosa creada queda con un id retornable."""
        resp = client_con_overrides.post(
            "/analizar",
            data={
                "eps": "FAMISANAR", "etapa": "RESPUESTA",
                "tabla_excel": "TA0201 texto suficiente",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "glosa_id" in data
        assert data["glosa_id"] is not None
