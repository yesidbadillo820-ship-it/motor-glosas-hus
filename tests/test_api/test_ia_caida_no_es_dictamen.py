"""Incidente 04-08-2026: un 401 del proveedor quedó GUARDADO como
«argumentación jurídica» con sello de calidad (glosa PPL, $97.671).

Estas pruebas sellan las dos capas del arreglo: (1) la IA caída lanza un
error limpio con causa legible y el análisis responde 503 sin guardar
NADA; (2) aunque un texto con firma de error de proveedor llegara por
cualquier camino (caché envenenado, código viejo), la persistencia lo
rechaza — jamás vuelve a existir un dictamen que diga «Invalid API Key».
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.models.schemas import GlosaResult
from app.services.glosa_service import (
    IANoDisponibleError,
    _mensaje_ia_caida,
    texto_con_error_de_proveedor,
)

ERROR_401 = "Error code: 401 - {'error': {'message': 'Invalid API Key', 'type': 'invalid_request_error', 'code': 'invalid_api_key'}}"


class TestCausasLegibles:
    def test_clave_invalida_dice_que_hacer(self):
        m = _mensaje_ia_caida(Exception(ERROR_401))
        assert "clave" in m and "NO se guardó" in m and "ANTHROPIC_API_KEY" in m

    def test_saturacion_dice_reintentar(self):
        assert "reintentá" in _mensaje_ia_caida(Exception("rate limit exceeded (429)")).lower()

    def test_detector_de_firmas(self):
        assert texto_con_error_de_proveedor(ERROR_401)
        assert texto_con_error_de_proveedor("ARGUMENTO: error code: 529 overloaded_error")
        assert not texto_con_error_de_proveedor(
            "LA E.S.E. HUS NO ACEPTA LA GLOSA. PRIMERO: EL SERVICIO FUE PRESTADO."
        )


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


def _cliente(db_session, service):
    from app.api.deps import get_usuario_actual
    from app.api.routers.analizar import get_glosa_service
    from app.main import app

    u = UsuarioRecord(id=1, email="ivan@hus.gov.co", nombre="I", rol="AUDITOR", activo=1)
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: u
    app.dependency_overrides[get_glosa_service] = lambda: service
    return TestClient(app)


def _analizar(cliente):
    return cliente.post(
        "/analizar",
        data={
            "eps": "PPL",
            "etapa": "INICIAL",
            "valor_aceptado": "0",
            "tabla_excel": "SO0201 — Se genera glosa al servicio 890701 por $97.671 sin respaldo.",
        },
    )


class TestIACaidaEs503SinGuardar:
    def test_el_caso_del_incidente(self, db_session):
        from app.main import app

        svc = MagicMock()
        svc.analizar = AsyncMock(
            side_effect=IANoDisponibleError(_mensaje_ia_caida(Exception(ERROR_401)))
        )
        with _cliente(db_session, svc) as c:
            r = _analizar(c)
        app.dependency_overrides.clear()

        assert r.status_code == 503
        assert "clave" in r.json()["detail"]
        assert "NO se guardó" in r.json()["detail"]
        # Y de verdad no se guardó NADA
        assert db_session.query(GlosaRecord).count() == 0


class TestElCinturonDePersistencia:
    def test_dictamen_con_firma_de_error_no_se_guarda(self, db_session):
        """Aunque el servicio devolviera el error como texto (caché viejo,
        camino no previsto), la persistencia lo rechaza."""
        from app.main import app

        svc = MagicMock()
        svc.analizar = AsyncMock(
            return_value=GlosaResult(
                tipo="RESPUESTA RE9901",
                resumen="x",
                dictamen=f"<div>ARGUMENTACIÓN JURÍDICA: {ERROR_401}</div>",
                codigo_glosa="SO0201",
                valor_objetado="$ 97.671",
                paciente="N/A",
                mensaje_tiempo="EN TÉRMINOS",
                color_tiempo="green",
                score=43.0,
                dias_restantes=10,
                modelo_ia="mock/test",
            )
        )
        with _cliente(db_session, svc) as c:
            r = _analizar(c)
        app.dependency_overrides.clear()

        assert r.status_code == 503
        assert "NO se" in r.json()["detail"]
        assert db_session.query(GlosaRecord).count() == 0


class TestCaratulaSinArgumentoNoEsDictamen:
    """Incidente 04-08-2026 (segunda parte): con la IA caída el motor armó
    la carátula completa —tabla, sello «VALIDADO POR QUALITY GATE», cierre—
    con la ARGUMENTACIÓN JURÍDICA VACÍA, y eso quedó guardado. Una carátula
    sin argumento no es un dictamen."""

    def test_el_constructor_se_niega_a_armar_caratula_vacia(self):
        from app.services.glosa_service import DictamenSinArgumentoError, GlosaService

        svc = GlosaService(groq_api_key=None, anthropic_api_key=None, primary_ai="groq")
        for vacio in ("", "   ", "<div></div>", "&nbsp; &nbsp;", "corto"):
            with pytest.raises(DictamenSinArgumentoError):
                svc._generar_dictamen_html(
                    codigo="TA2901",
                    valor="$ 42.800",
                    cod_res="RE9901",
                    desc_res="GLOSA NO ACEPTADA",
                    argumento=vacio,
                    eps="PPL",
                    tipo="TA_TARIFA",
                )

    def test_con_argumento_real_sí_arma(self):
        from app.services.glosa_service import GlosaService

        svc = GlosaService(groq_api_key=None, anthropic_api_key=None, primary_ai="groq")
        html = svc._generar_dictamen_html(
            codigo="TA2901",
            valor="$ 42.800",
            cod_res="RE9901",
            desc_res="GLOSA NO ACEPTADA",
            argumento=(
                "LA E.S.E. HUS NO ACEPTA LA GLOSA. PRIMERO: EL EQUIPO DE BOMBA DE "
                "INFUSIÓN CORRESPONDE A UN INSUMO FACTURADO CONFORME A LA TARIFA "
                "INSTITUCIONAL VIGENTE. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
            ),
            eps="PPL",
            tipo="TA_TARIFA",
        )
        assert "ARGUMENTACIÓN JURÍDICA" in html and "BOMBA DE INFUSIÓN" in html

    def test_el_endpoint_no_guarda_caratula_vacia(self, db_session):
        """Aunque la carátula vacía llegara armada desde otro camino."""
        from app.main import app

        caratula_vacia = (
            "<table><tr><td>TA2901</td></tr></table>"
            '<h4>ARGUMENTACIÓN JURÍDICA</h4><div style="x">   </div>'
            "<div>Nota: Generado con asistencia de IA.</div>"
        )
        svc = MagicMock()
        svc.analizar = AsyncMock(
            return_value=GlosaResult(
                tipo="RESPUESTA RE9901",
                resumen="ok",
                dictamen=caratula_vacia,
                codigo_glosa="TA2901",
                valor_objetado="$ 42.800",
                paciente="N/A",
                mensaje_tiempo="EN TÉRMINOS",
                color_tiempo="green",
                score=43.0,
                dias_restantes=10,
                modelo_ia="mock/test",
            )
        )
        with _cliente(db_session, svc) as c:
            r = _analizar(c)
        app.dependency_overrides.clear()

        assert r.status_code == 503
        assert "argumentación" in r.json()["detail"].lower()
        assert db_session.query(GlosaRecord).count() == 0


class TestElMensajeNombraATodosLosProveedores:
    """Incidente 04-08 (tercera parte): con Groq como principal y Anthropic
    de respaldo, si fallaban los dos el mensaje solo nombraba al último —
    el auditor veía «Invalid API Key» de un proveedor que ni siquiera es el
    suyo y no sabía qué había pasado con Groq."""

    def test_nombra_cada_proveedor_con_su_causa(self):
        from app.services.glosa_service import _mensaje_ia_caida

        fallos = [
            ("groq", Exception("rate limit exceeded (429)")),
            ("anthropic", Exception(ERROR_401)),
        ]
        m = _mensaje_ia_caida(fallos[-1][1], fallos)
        assert "GROQ" in m and "límite de uso" in m
        assert "ANTHROPIC" in m and "inválida o vencida" in m
        assert "NO se guardó" in m

    def test_causas_traducidas(self):
        from app.services.glosa_service import _causa_corta

        assert "saldo" in _causa_corta(Exception("insufficient_quota: no credit"))
        assert "saturado" in _causa_corta(Exception("overloaded_error 529"))
        assert "a tiempo" in _causa_corta(Exception("Request timed out"))
        assert "red" in _causa_corta(Exception("Connection refused"))

    def test_sin_lista_sigue_funcionando(self):
        """Compatibilidad: un solo error sin lista da el mensaje de antes."""
        from app.services.glosa_service import _mensaje_ia_caida

        assert "clave" in _mensaje_ia_caida(Exception(ERROR_401))
