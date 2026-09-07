"""Escudos de resiliencia del Auto-Pilot (hotfix 03-09-2026).

Condición del auditor para encender AUTO_PILOT_ENABLED:

1. TRAZABILIDAD DEL FALLBACK — cada fila de la bitácora registra
   `modelo_utilizado`: el modelo que produjo el dictamen decidido (Claude de
   Anthropic o el fallback de Groq, tal como quedó en historial.modelo_ia).
2. BLOQUEO DEL INDEXADOR — si el indexador de soportes reporta
   «construyendo: true» (o su estado no se puede leer), el ciclo del worker
   aborta ENTERO: sin evaluar, sin escribir, sin registrar.
3. CORTACIRCUITO OCR — un timeout o desconexión (WinError) leyendo soportes
   con Gemini detiene la glosa de inmediato: queda en
   PENDIENTE_APROBACION_HUMANA marcada con la etiqueta ERROR_OCR, sin
   dictamen a ciegas.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import AutoPilotBitacoraRecord, GlosaRecord
from app.services import auto_pilot_worker as W
from app.services.pdf_service import (
    ETIQUETA_ERROR_OCR,
    ErrorOCR,
    PdfService,
    _es_corte_de_red,
)


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


def _glosa(db, **kw):
    base = dict(
        eps="NUEVA EPS",
        factura="HUS1",
        codigo_glosa="TA0201",
        valor_objetado=100000.0,
        estado="PENDIENTE",
        workflow_state="RADICADA",
        dictamen="<div>ESE HUS NO ACEPTA LA GLOSA…</div>",
        modelo_ia="groq/llama-3.3-70b-versatile",
    )
    base.update(kw)
    g = GlosaRecord(**base)
    db.add(g)
    db.commit()
    return g


def _stub_evaluador(monkeypatch, confianza=0.95, estado="LISTA_ENVIAR"):
    import app.services.autopilot_service as aps
    import app.services.riesgo_ratificacion as rr

    monkeypatch.setattr(
        aps,
        "evaluar_glosa_autopilot",
        lambda db, g: SimpleNamespace(
            estado=estado,
            confianza=confianza,
            razones_a_favor=[],
            razones_en_contra=["señal en contra"],
            detalle={"plantillas_gold": 2, "calidad_dictamen": {"ok": True}},
        ),
    )
    monkeypatch.setattr(
        rr, "calcular_riesgo", lambda **kw: {"nivel": "BAJO", "score": 10, "factores": []}
    )


def _stub_indexador(monkeypatch, construyendo=False, explota=False):
    import app.services.soportes_autodiscovery_service as sas

    class _Idx:
        def stats(self):
            if explota:
                raise RuntimeError("índice sin inicializar")
            return {"construyendo": construyendo, "facturas_indexadas": 10}

    monkeypatch.setattr(sas, "get_indexer", lambda: _Idx())


# ══════════════════════════════════════════════════════════════════════════
#  Escudo 1 — trazabilidad del fallback de modelos en la bitácora
# ══════════════════════════════════════════════════════════════════════════


class TestEscudo1_TrazabilidadFallback:
    def test_la_columna_existe_en_el_modelo(self):
        assert hasattr(AutoPilotBitacoraRecord, "modelo_utilizado")

    def test_candidata_lleva_el_modelo_anthropic(self, db, monkeypatch):
        _stub_evaluador(monkeypatch)
        g = _glosa(db, modelo_ia="claude-sonnet-4-5")
        decision = W.evaluar_candidata(db, g)
        assert decision["decision"] == "CANDIDATA"
        assert decision["modelo_utilizado"] == "claude-sonnet-4-5"

    def test_rechazo_lleva_el_modelo_del_fallback_groq(self, db, monkeypatch):
        _stub_evaluador(monkeypatch, confianza=0.50)
        g = _glosa(db, modelo_ia="groq/llama-3.3-70b-versatile")
        decision = W.evaluar_candidata(db, g)
        assert decision["decision"] == "RECHAZADA"
        assert decision["modelo_utilizado"] == "groq/llama-3.3-70b-versatile"

    def test_procesar_persiste_modelo_utilizado_en_la_bitacora(self, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        _stub_indexador(monkeypatch, construyendo=False)
        _glosa(db, modelo_ia="claude-sonnet-4-5")
        W.procesar(db)
        fila = db.query(AutoPilotBitacoraRecord).order_by(AutoPilotBitacoraRecord.id.desc()).first()
        assert fila is not None
        assert fila.modelo_utilizado == "claude-sonnet-4-5"

    def test_liberacion_humana_tambien_queda_con_su_modelo(self, db, monkeypatch):
        g = _glosa(db, workflow_state=W.ESTADO_CUARENTENA, modelo_ia="groq/llama-3.3-70b-versatile")
        W.liberar(db, g.id, "gestor@hus.gov.co")
        fila = (
            db.query(AutoPilotBitacoraRecord)
            .filter(AutoPilotBitacoraRecord.decision == "LIBERADA_POR_HUMANO")
            .first()
        )
        assert fila is not None
        assert fila.modelo_utilizado == "groq/llama-3.3-70b-versatile"

    def test_el_dto_de_la_bitacora_expone_modelo_utilizado(self):
        from app.api.routers.autopilot import BitacoraDecisionDTO

        assert "modelo_utilizado" in BitacoraDecisionDTO.model_fields


# ══════════════════════════════════════════════════════════════════════════
#  Escudo 2 — bloqueo del ciclo con el indexador a medio construir
# ══════════════════════════════════════════════════════════════════════════


class TestEscudo2_BloqueoIndexador:
    def test_construyendo_true_aborta_sin_tocar_la_base(self, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_indexador(monkeypatch, construyendo=True)

        class DBQueNoSePuedeTocar:
            def __getattr__(self, nombre):
                raise AssertionError(f"el worker tocó la base ({nombre}) con el índice a medias")

        parte = W.procesar(DBQueNoSePuedeTocar())
        assert parte["estado"] == "abortado_por_indexador"
        assert "construyendo" in parte["detalle"]

    def test_construyendo_true_no_deja_filas_ni_muta_glosas(self, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        _stub_indexador(monkeypatch, construyendo=True)
        g = _glosa(db)
        W.procesar(db)
        db.refresh(g)
        assert g.workflow_state == "RADICADA"
        assert db.query(AutoPilotBitacoraRecord).count() == 0

    def test_estado_ilegible_tambien_aborta(self, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_indexador(monkeypatch, explota=True)
        parte = W.procesar(object())
        assert parte["estado"] == "abortado_por_indexador"
        assert "ilegible" in parte["detalle"]

    def test_con_el_indice_quieto_el_ciclo_corre(self, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        _stub_indexador(monkeypatch, construyendo=False)
        g = _glosa(db)
        parte = W.procesar(db)
        db.refresh(g)
        assert parte["estado"] == "ok"
        assert parte["en_cuarentena"] == 1
        assert g.workflow_state == W.ESTADO_CUARENTENA

    def test_el_flag_apagado_sigue_mandando_sobre_todo(self, monkeypatch):
        monkeypatch.delenv("AUTO_PILOT_ENABLED", raising=False)
        _stub_indexador(monkeypatch, construyendo=True)
        parte = W.procesar(object())
        assert parte["estado"] == "deshabilitado"


# ══════════════════════════════════════════════════════════════════════════
#  Escudo 3 — cortacircuito del OCR de Gemini
# ══════════════════════════════════════════════════════════════════════════


class TestEscudo3_DetectorDeCortes:
    def test_timeout_y_desconexiones_disparan(self):
        assert _es_corte_de_red(httpx.ReadTimeout("lento")) is True
        assert _es_corte_de_red(httpx.ConnectError("rechazado")) is True
        assert _es_corte_de_red(ConnectionResetError("se cayó")) is True
        assert _es_corte_de_red(TimeoutError()) is True

    def test_winerror_de_windows_dispara(self):
        assert _es_corte_de_red(OSError("[WinError 10054] conexión forzada por el host")) is True
        assert _es_corte_de_red(RuntimeError("WinError 10060: timed out")) is True

    def test_errores_de_api_con_respuesta_no_disparan(self):
        assert _es_corte_de_red(RuntimeError("Gemini HTTP 429: cuota agotada")) is False
        assert _es_corte_de_red(ValueError("clave inválida")) is False


class TestEscudo3_Cortacircuito:
    def _pdf_escaneado(self, monkeypatch):
        async def _sin_texto(self, contenido):
            return ""

        monkeypatch.setattr(PdfService, "extraer", _sin_texto)

    def test_corte_de_red_en_gemini_levanta_error_ocr(self, monkeypatch):
        self._pdf_escaneado(monkeypatch)

        async def _gemini_cae(self, pdf_bytes, api_key, model):
            raise httpx.ReadTimeout("Gemini no respondió")

        monkeypatch.setattr(PdfService, "_ocr_gemini", _gemini_cae)
        with pytest.raises(ErrorOCR):
            asyncio.run(
                PdfService().extraer_con_ocr(b"%PDF-1.4 fake", gemini_api_key="clave-prueba")
            )

    def test_error_de_api_no_dispara_y_se_sigue_como_antes(self, monkeypatch):
        self._pdf_escaneado(monkeypatch)

        async def _gemini_rechaza(self, pdf_bytes, api_key, model):
            raise RuntimeError("Gemini HTTP 400: PDF no admitido")

        monkeypatch.setattr(PdfService, "_ocr_gemini", _gemini_rechaza)
        texto, metodo = asyncio.run(
            PdfService().extraer_con_ocr(b"%PDF-1.4 fake", gemini_api_key="clave-prueba")
        )
        assert metodo == "vacio"

    def test_extraer_pdfs_no_se_traga_el_cortacircuito(self, monkeypatch):
        from app.api.routers.analizar import _extraer_pdfs

        async def _revienta(self, contenido, **kw):
            raise ErrorOCR("OCR de Gemini cortado por red (ReadTimeout)")

        monkeypatch.setattr(PdfService, "extraer_con_ocr", _revienta)

        class _Archivo:
            filename = "soporte.pdf"

            async def read(self):
                return b"%PDF-1.4 fake"

        with pytest.raises(ErrorOCR):
            asyncio.run(_extraer_pdfs([_Archivo()], "req-test"))

    def test_analizar_impl_detiene_la_glosa_ante_error_ocr(self):
        from app.api.routers import analizar as mod

        fuente = inspect.getsource(mod._analizar_impl)
        assert "except ErrorOCR" in fuente
        assert "_marcar_glosa_error_ocr" in fuente


class TestEscudo3_GlosaDetenida:
    def test_glosa_existente_muta_a_cuarentena_con_etiqueta(self, db):
        from app.api.routers.analizar import _marcar_glosa_error_ocr

        g = _glosa(db, factura="HUS777", etapa="OBJECION")
        gid = _marcar_glosa_error_ocr(
            db,
            numero_factura="HUS777",
            etapa="OBJECION",
            eps="NUEVA EPS",
            tabla_excel="SO0101 | soporte",
            detalle="OCR de Gemini cortado por red (ReadTimeout)",
            req_id="req-test",
        )
        db.refresh(g)
        assert gid == g.id
        assert g.workflow_state == W.ESTADO_CUARENTENA
        assert (g.nota_workflow or "").startswith(ETIQUETA_ERROR_OCR)

    def test_glosa_nueva_queda_creada_sin_dictamen_y_marcada(self, db):
        from app.api.routers.analizar import _marcar_glosa_error_ocr

        gid = _marcar_glosa_error_ocr(
            db,
            numero_factura="HUS888",
            etapa="OBJECION",
            eps="COOSALUD",
            tabla_excel="SO0101 | Falta epicrisis por $150.000",
            detalle="OCR de Gemini cortado por red (WinError 10054)",
            req_id="req-test",
        )
        g = db.query(GlosaRecord).filter(GlosaRecord.id == gid).first()
        assert g is not None
        assert g.dictamen is None  # jamás un dictamen a ciegas
        assert g.workflow_state == W.ESTADO_CUARENTENA
        assert (g.nota_workflow or "").startswith(ETIQUETA_ERROR_OCR)
        assert g.codigo_glosa == "SO0101"

    def test_el_worker_no_evalua_una_glosa_detenida_por_ocr(self, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        _stub_indexador(monkeypatch, construyendo=False)
        detenida = _glosa(
            db,
            factura="HUS999",
            dictamen=None,
            workflow_state=W.ESTADO_CUARENTENA,
            nota_workflow=f"{ETIQUETA_ERROR_OCR}: corte de red",
        )
        W.procesar(db)
        filas = (
            db.query(AutoPilotBitacoraRecord)
            .filter(AutoPilotBitacoraRecord.glosa_id == detenida.id)
            .count()
        )
        assert filas == 0
