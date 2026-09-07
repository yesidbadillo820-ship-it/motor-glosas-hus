"""Hotfix analisis-rag-ceguera (03-09-2026) — caso TA0301.

Tres bloqueos ordenados por el auditor tras un dictamen redactado a ciegas:

1. CEGUERA TEMPORAL — REVERTIDO EL 04-09-2026. Aquel candado devolvía
   HTTP 423 mientras el indexador trabajaba. La intención era buena pero la
   medida fue desproporcionada: el escaneo dura HORAS y paralizaba toda la
   operación. Se quitó. Lo que queda —y es lo correcto— es la protección POR
   FACTURA en glosa_service: mientras el índice se arma, el dictamen no
   afirma que falte un soporte, pero el análisis SÍ corre.
2. ERROR HUMANO: si el Quality Gate encuentra hallazgos graves o la
   confianza no supera el umbral, el botón «Marcar como RESPONDIDA» queda
   deshabilitado (gris) — contrato verificado sobre el frontend.
3. RAG NORMATIVO: el system prompt prohíbe citar artículos, leyes o
   incisos que no estén textualmente en el contexto inyectado (el modelo
   alucinó el Art. 20 del Decreto 4747 cuando el correcto era el 23).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.database import Base, get_db
from app.main import app
from app.services.glosa_service import IANoDisponibleError

RAIZ = Path(__file__).resolve().parents[2]

TEXTO_GLOSA = (
    "TA0301 | HUS495060 | Mayor valor cobrado en la consulta de urgencias por "
    "especialista frente a la tarifa pactada. Valor objetado: $180.000. "
    "Se objeta el valor facturado por diferencia de tarifas del procedimiento."
)


class _ServicioCentinela:
    """Si el endpoint llega hasta el LLM, este centinela lo delata."""

    def __init__(self):
        self.llamado = False

    async def analizar(self, *a, **kw):
        self.llamado = True
        raise IANoDisponibleError("centinela: el flujo llegó hasta la IA")


def _stub_indexador(monkeypatch, construyendo):
    import app.services.soportes_autodiscovery_service as sas

    class _Idx:
        def stats(self):
            return {"construyendo": construyendo, "facturas_indexadas": 5}

        def lookup(self, factura, auto_rebuild=True):
            return []

    monkeypatch.setattr(sas, "get_indexer", lambda: _Idx())


@pytest.fixture
def entorno():
    from app.api.routers.analizar import get_glosa_service

    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    sesion = sessionmaker(bind=eng)()
    auditor = SimpleNamespace(email="auditor@hus.gov.co", rol="AUDITOR", nombre="A", activo=1)
    centinela = _ServicioCentinela()

    app.dependency_overrides[get_db] = lambda: sesion
    app.dependency_overrides[deps.get_usuario_actual] = lambda: auditor
    app.dependency_overrides[deps.get_auditor_o_superior] = lambda: auditor
    app.dependency_overrides[get_glosa_service] = lambda: centinela
    try:
        yield TestClient(app), centinela
    finally:
        for dep in (
            get_db,
            deps.get_usuario_actual,
            deps.get_auditor_o_superior,
            get_glosa_service,
        ):
            app.dependency_overrides.pop(dep, None)
        sesion.close()
        eng.dispose()


def _post_analizar(cliente):
    return cliente.post(
        "/analizar",
        data={
            "eps": "COOSALUD",
            "etapa": "OBJECION",
            "tabla_excel": TEXTO_GLOSA,
            "numero_factura": "HUS495060",
            "valor_aceptado": "0",
        },
    )


class TestElIndexadorYaNoParalizaNada:
    """04-09-2026: el candado global se destruyó. Estas pruebas impiden que
    vuelva — un análisis NO se aborta porque el índice esté trabajando."""

    def test_con_el_indice_construyendo_el_analisis_SIGUE(self, entorno, monkeypatch):
        cliente, centinela = entorno
        _stub_indexador(monkeypatch, construyendo=True)
        r = _post_analizar(cliente)
        assert r.status_code != 423, (
            "volvió el candado global: el escaneo dura horas y esto paraliza la operación entera"
        )
        # Llegó hasta la IA (el centinela levanta IANoDisponibleError → 503).
        assert centinela.llamado is True, "el análisis se detuvo antes de la IA"

    def test_con_el_indice_quieto_tambien(self, entorno, monkeypatch):
        cliente, centinela = entorno
        _stub_indexador(monkeypatch, construyendo=False)
        r = _post_analizar(cliente)
        assert r.status_code == 503, r.text
        assert centinela.llamado is True

    def test_sin_indexador_tampoco_se_bloquea(self, entorno, monkeypatch):
        import app.services.soportes_autodiscovery_service as sas

        cliente, centinela = entorno

        def _explota():
            raise RuntimeError("indexador sin inicializar")

        monkeypatch.setattr(sas, "get_indexer", _explota)
        r = _post_analizar(cliente)
        assert r.status_code == 503
        assert centinela.llamado is True

    def test_una_glosa_sin_pdfs_se_defiende_igual(self, entorno, monkeypatch):
        """El caso real del auditor: glosas de prueba sin un solo soporte.

        El motor tiene que argumentar con el texto, los CUPS y la norma — no
        quedarse esperando un expediente que no existe.
        """
        cliente, centinela = entorno
        _stub_indexador(monkeypatch, construyendo=True)  # y encima escaneando
        r = _post_analizar(cliente)
        assert r.status_code != 423
        assert centinela.llamado is True, (
            "sin PDFs el motor se bloqueó en vez de defender con lo que hay"
        )

    def test_el_candado_no_esta_en_el_codigo(self):
        """Guardia de texto: que nadie lo reponga sin darse cuenta."""
        import inspect

        from app.api.routers import analizar as mod

        fuente = inspect.getsource(mod._analizar_impl)
        assert "status_code=423" not in fuente, "volvió el HTTP 423 al endpoint"


class TestRefuerzoRagNormativo:
    def test_el_system_prompt_prohibe_articulos_de_memoria(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "PROHIBIDO CITAR NÚMEROS DE ARTÍCULO" in SYSTEM_BASE
        assert "TEXTUALMENTE" in SYSTEM_BASE
        assert "inciso" in SYSTEM_BASE and "numeral" in SYSTEM_BASE
        # El caso real que originó el hotfix queda documentado en el prompt:
        assert "Art. 20 del Decreto 4747" in SYSTEM_BASE
        # Y la salida correcta cuando el número no está en el contexto:
        assert "SIN número" in SYSTEM_BASE

    def test_la_regla_vieja_de_no_inventar_normas_sigue_intacta(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "PROHIBIDO INVENTAR NORMAS" in SYSTEM_BASE


class TestBotonEstadoFinalBloqueado:
    """Contrato del frontend: el botón de estado final se apaga solo."""

    @pytest.fixture(scope="class")
    def html(self):
        return (RAIZ / "static" / "index.html").read_text(encoding="utf-8")

    def test_umbral_de_confianza_declarado(self, html):
        assert "UMBRAL_CONFIANZA_RESPONDIDA = 0.85" in html

    def test_los_bloqueos_se_calculan_en_un_solo_lugar(self, html):
        assert "_bloqueosEstadoFinal" in html
        # QG graves (severidad alta / puntaje rojo) y confianza baja:
        assert "severidad === 'alta'" in html
        assert "no supera el umbral" in html

    def test_el_boton_continuar_se_deshabilita_gris(self, html):
        assert "aud-continuar" in html
        assert "disabled" in html
        # El gris del botón bloqueado y su explicación visible:
        assert "#9ca3af" in html
        assert "Bloqueado por seguridad" in html

    def test_auditar_y_confirmar_consulta_la_confianza(self, html):
        assert "/autopilot/glosa/" in html
