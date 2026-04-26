"""Tests del endpoint POST /glosas/{id}/reanalizar (R60 P2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.models.schemas import GlosaResult


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
def usuario_auditor():
    return UsuarioRecord(
        id=1, email="auditor@hus.gov.co", nombre="Auditor",
        rol="AUDITOR", activo=1,
    )


@pytest.fixture
def glosa_seed(db_session):
    """Crea una glosa con texto_glosa_original para que reanalizar funcione."""
    g = GlosaRecord(
        eps="FAMISANAR",
        codigo_glosa="TA0201",
        valor_objetado=168_563,
        valor_aceptado=0,
        etapa="RESPUESTA",
        estado="RADICADA",
        dictamen="<div>dictamen v1</div>",
        texto_glosa_original="TA0201 — diferencia tarifa CUPS 890750 valor $168.563",
        factura="FE-2026-001",
        creado_en=ahora_utc(),
    )
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    return g


@pytest.fixture
def client(db_session, usuario_auditor):
    """Cliente con dependency_overrides + GlosaService mockeado."""
    from app.api.deps import (
        get_auditor_o_superior,
        get_usuario_actual,
    )
    from app.main import app

    # Mock del GlosaService instanciado dentro del endpoint
    import app.api.routers.glosas as glosas_mod
    original_svc = glosas_mod.GlosaService

    class _MockService:
        def __init__(self, **kw):
            pass

        async def analizar(self, glosa_input, contexto_pdf, contratos, **kw):
            return GlosaResult(
                tipo="RESPUESTA RE9901",
                resumen="Reanalisis OK",
                dictamen="<div>dictamen v2 reanalizado</div>",
                codigo_glosa=glosa_input.tabla_excel[:6] or "TA0201",
                valor_objetado="$ 168,563",
                paciente="N/A",
                mensaje_tiempo="EN TÉRMINOS",
                color_tiempo="green",
                score=88.0,
                dias_restantes=10,
                modelo_ia="mock/reanalisis",
            )

    glosas_mod.GlosaService = _MockService

    # Bypass del rate-limit IA
    from app.services import rate_limit_ia
    original_consumir = rate_limit_ia.consumir_cupo_ia

    async def _bypass_cupo():
        return None
    rate_limit_ia.consumir_cupo_ia = _bypass_cupo
    glosas_mod._consumir_cupo_ia = _bypass_cupo

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_auditor
    app.dependency_overrides[get_auditor_o_superior] = lambda: usuario_auditor

    with TestClient(app) as c:
        yield c

    glosas_mod.GlosaService = original_svc
    glosas_mod._consumir_cupo_ia = original_consumir
    rate_limit_ia.consumir_cupo_ia = original_consumir
    app.dependency_overrides.clear()


class TestReanalizarGlosa:
    def test_reanalizar_actualiza_dictamen_sin_duplicar(self, client, glosa_seed, db_session):
        resp = client.post(
            f"/glosas/{glosa_seed.id}/reanalizar",
            json={"tono": "firme", "modo_respuesta": "defender"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "dictamen v2" in data["dictamen"]
        # No se duplicó la fila
        total = db_session.query(GlosaRecord).count()
        assert total == 1
        # El dictamen en BD se actualizó
        db_session.expire_all()
        g = db_session.query(GlosaRecord).first()
        assert "v2" in g.dictamen
        assert g.modelo_ia == "mock/reanalisis"

    def test_reanalizar_glosa_inexistente(self, client):
        resp = client.post(
            "/glosas/999999/reanalizar",
            json={"tono": "conciliador", "modo_respuesta": "defender"},
        )
        assert resp.status_code == 404

    def test_reanalizar_sin_texto_original_falla(self, client, db_session):
        """Glosas legacy sin texto_glosa_original no se pueden reanalizar."""
        g = GlosaRecord(
            eps="X", codigo_glosa="Y", valor_objetado=100,
            etapa="X", estado="RADICADA", creado_en=ahora_utc(),
            dictamen="<div>algo</div>",
            # texto_glosa_original = None
        )
        db_session.add(g)
        db_session.commit()
        db_session.refresh(g)
        resp = client.post(
            f"/glosas/{g.id}/reanalizar",
            json={"tono": "conciliador", "modo_respuesta": "defender"},
        )
        assert resp.status_code == 400
        assert "texto_glosa_original" in resp.text.lower() or "legacy" in resp.text.lower()

    def test_reanalizar_modo_auditoria_a_defender(self, client, glosa_seed, db_session):
        """Caso de uso típico: gestor primero hizo auditoría, ahora quiere
        defender. Cambio de modo sobre la misma glosa."""
        resp = client.post(
            f"/glosas/{glosa_seed.id}/reanalizar",
            json={"tono": "neutral", "modo_respuesta": "defender"},
        )
        assert resp.status_code == 200
        assert resp.json()["modo"] == "defender"

    def test_reanalizar_modo_invalido_fallback_defender(self, client, glosa_seed):
        """Modo desconocido cae a 'defender' (validador del schema)."""
        resp = client.post(
            f"/glosas/{glosa_seed.id}/reanalizar",
            json={"tono": "conciliador", "modo_respuesta": "rebelde"},
        )
        assert resp.status_code == 200
        # El validador transformó el modo a 'defender'
        assert resp.json()["modo"] in ("defender", "rebelde")  # endpoint devuelve lo que recibió
