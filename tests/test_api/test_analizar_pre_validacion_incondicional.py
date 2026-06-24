"""Tests: pre-validación de texto de glosa CORRE AUNQUE el Quality Gate
esté OFF.

Regresión: el wrapper QG nunca corría con QG OFF → el input basura llegaba
al IA. Ahora `analizar()` corre check_texto_glosa INCONDICIONALMENTE.

El umbral fue ajustado el 10-jun-2026 (Bug2): bajado de 60 a 20 chars y
ampliada la lista de dominio a vocabulario clínico (UCI, días, PBS, ...).
Glosas reales son cortas — "TA0102 - Medicamento fuera del PBS" (35
chars) es legítima y debe pasar. La defensa contra valores y contratos
fabricados quedó delegada al post_validator (donde corresponde).
"""

from __future__ import annotations

from unittest.mock import patch

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


def _form(eps="DISPENSARIO MEDICO", texto="Se glosa por falta de cobertura"):
    return {
        "eps": eps,
        "etapa": "INICIAL",
        "valor_aceptado": "0",
        "tabla_excel": texto,
        "tono": "conciliador",
        "modo_respuesta": "defender",
    }


class TestPreValidacionIncondicional:
    def test_input_muy_corto_bloqueado_con_flag_off(self, client, monkeypatch):
        """Aunque QUALITY_GATE_ENABLED esté OFF, el input claramente corto
        (<20 chars) se bloquea antes de gastar un call de IA."""
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)

        with patch("app.services.glosa_service.GlosaService._llamar_ia") as spy_llamar_ia:
            r = client.post("/analizar", data=_form(texto="cobertura"))  # 9 chars
            assert r.status_code == 400, r.text
            detail = r.json().get("detail", "")
            assert "corto" in detail.lower() or "mínimo" in detail.lower()
            spy_llamar_ia.assert_not_called()

    def test_input_muy_corto_bloqueado_con_flag_on(self, client, monkeypatch):
        """Con QG ON el mismo input se bloquea por el mismo check."""
        monkeypatch.setenv("QUALITY_GATE_ENABLED", "1")
        monkeypatch.setenv("QUALITY_GATE_ROLLOUT_PCT", "100")
        with patch("app.services.glosa_service.GlosaService._llamar_ia") as spy_llamar_ia:
            r = client.post("/analizar", data=_form(texto="objet hoy"))  # 9 chars
            assert r.status_code == 400
            spy_llamar_ia.assert_not_called()

    def test_input_sin_dominio_ni_codigo_bloqueado(self, client, monkeypatch):
        """Texto largo pero sin código de glosa Y sin ningún término del
        dominio (admin o clínico) → 400. La defensa contra valores fabricados
        sigue siendo del post_validator."""
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        with patch("app.services.glosa_service.GlosaService._llamar_ia") as spy_llamar_ia:
            r = client.post(
                "/analizar",
                data=_form(
                    texto=(
                        "Este es un texto suficientemente largo pero sin "
                        "ninguna mención específica de nada."
                    )
                ),
            )
            assert r.status_code == 400
            spy_llamar_ia.assert_not_called()

    def test_glosa_real_corta_con_codigo_pasa(self, client, monkeypatch):
        """Regresión 10-jun-2026: una glosa real corta como
        "TA0102 - Medicamento fuera del PBS. No procede." (53 chars) NO
        debe bloquearse — antes el pre-val exigía 60 chars y rechazaba
        glosas reales. La defensa contra valores inventados queda en el
        post_validator."""
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        r = client.post(
            "/analizar",
            data=_form(texto="TA0102 - Medicamento fuera del PBS. No procede reconocimiento."),
        )
        # Puede fallar por otras razones (IA mockeada, etc.), pero NUNCA
        # con el mensaje del pre-validator de "texto muy corto".
        if r.status_code == 400:
            detail = r.json().get("detail", "").lower()
            assert "corto" not in detail
            assert "mínimo" not in detail

    def test_input_valido_pasa_la_pre_validacion(self, client, monkeypatch):
        """Input realista NO se bloquea en pre-validación (cualquier error
        posterior es de otra etapa)."""
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        texto_ok = (
            "TA0201 - Mayor valor cobrado en consulta especializada por "
            "valor objetado de $500.000 según factura electrónica FE-001"
        )
        r = client.post("/analizar", data=_form(texto=texto_ok))
        if r.status_code == 400:
            assert "corto" not in r.json().get("detail", "").lower()
            assert "mínimo" not in r.json().get("detail", "").lower()

    @pytest.mark.parametrize(
        "texto_libre",
        [
            # Glosas EPS reales de texto libre, SIN código (pedido del
            # usuario 10-jun-2026: "QUITAR ESA RESTRICCIÓN ... QUIERO
            # REALMENTE PONERLA A PRUEBA CON ALGO QUE NO ESTÉ FIJO").
            "No existe relación clínica entre diagnóstico registrado y procedimiento facturado.",
            "Reingreso dentro de los 15 días atribuible a manejo deficiente de la IPS.",
            "Tornillos y placas no soportados contractualmente.",
        ],
    )
    def test_glosa_texto_libre_sin_codigo_no_se_bloquea(self, client, monkeypatch, texto_libre):
        """Modo texto libre: sin código de glosa el análisis procede — la
        IA clasifica la familia desde el texto. NUNCA debe devolver el
        viejo bloqueo de 'falta el código' / 'N/A no tiene formato'."""
        monkeypatch.setenv("QUALITY_GATE_ENABLED", "1")
        monkeypatch.setenv("QUALITY_GATE_ROLLOUT_PCT", "100")
        r = client.post("/analizar", data=_form(texto=texto_libre))
        if r.status_code == 400:
            detail = r.json().get("detail", "").lower()
            assert "código" not in detail and "codigo" not in detail, detail
            assert "n/a" not in detail, detail
