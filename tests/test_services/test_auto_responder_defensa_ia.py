"""Defensas anti-gasto IA en el flujo de import masivo.

Reportado por el dueño 12-jun-2026: el import disparó 251 calls de
claude-sonnet-4-6 ($14.50) en glosas que ya tenían respuesta determinística
o que eran idénticas a glosas ya respondidas. Tres capas de defensa
agregadas al `procesar_glosa` del auto_responder:

  1. texto_fijo_detector (RATIFICADAS / EXTEMPORÁNEAS)
  2. Reuso de gemelas (misma EPS+código+valor±10%+firma del concepto)
  3. IA_SOLO_COMPLEJAS=1 → SIMPLE/MEDIA → PENDIENTE_MANUAL sin tokens

También: el export del historial truncaba el dictamen a 800 chars
(visible: 713/809 dictámenes cortados a mitad de oración). Cap nuevo:
30.000 chars (Excel soporta 32.767).
"""

from __future__ import annotations

import importlib

from app.services.auto_responder_service import (
    _buscar_dictamen_gemelo,
    _firma_concepto,
)


class TestFirmaConcepto:
    def test_misma_firma_para_glosas_de_distinta_factura(self):
        # Lo único que cambia entre dos glosas del mismo concepto: la
        # factura y el valor. La firma debe ser idéntica.
        a = "CO0701 - MEDICAMENTO FUERA DEL POS. FACTURA HUS0000500123 $4.200"
        b = "CO0701 - MEDICAMENTO FUERA DEL POS. FACTURA HUS0000500999 $8.500"
        assert _firma_concepto(a) == _firma_concepto(b)

    def test_distinto_concepto_distinta_firma(self):
        a = "CO0701 - MEDICAMENTO FUERA DEL POS"
        b = "TA5801 - MAYOR VALOR COBRADO EN CONSULTA"
        assert _firma_concepto(a) != _firma_concepto(b)

    def test_vacio_no_revienta(self):
        assert _firma_concepto("") == _firma_concepto(None) == _firma_concepto("   ")


class TestBuscarDictamenGemelo:
    """Tests con BD sqlite en memoria — verifican la lógica de reuso."""

    def _setup_db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.database import Base
        from app.models import db as _models_db  # noqa: F401 — registra metadata

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        return sessionmaker(bind=engine)()

    def _crear_glosa(self, db, **kw):
        from app.models.db import GlosaRecord

        defaults = dict(
            eps="FAMISANAR EPS",
            codigo_glosa="CO0701",
            valor_objetado=4200.0,
            estado="RESPONDIDA",
            dictamen="A" * 500,
            texto_glosa_original="CO0701 - MEDICAMENTO FUERA DEL POS. CONCEPTO ESTÁNDAR.",
            codigo_respuesta="RE9901",
        )
        defaults.update(kw)
        g = GlosaRecord(**defaults)
        db.add(g)
        db.commit()
        db.refresh(g)
        return g

    def test_reusa_gemela_misma_firma_y_valor_similar(self):
        db = self._setup_db()
        try:
            previa = self._crear_glosa(db, valor_objetado=4200.0)
            # Glosa nueva: misma EPS+código, valor distinto pero dentro del
            # ±10%, mismo concepto modulo factura/$.
            nueva = self._crear_glosa(
                db,
                valor_objetado=4400.0,  # 4400/4200 = 1.047 — dentro de ±10%
                estado="PENDIENTE",
                dictamen="",
                texto_glosa_original="CO0701 - MEDICAMENTO FUERA DEL POS. CONCEPTO ESTÁNDAR.",
            )
            r = _buscar_dictamen_gemelo(db, nueva, nueva.texto_glosa_original)
            assert r is not None
            assert r["glosa_id"] == previa.id
            assert r["codigo_respuesta"] == "RE9901"
        finally:
            db.close()

    def test_no_reusa_si_valor_fuera_de_rango(self):
        db = self._setup_db()
        try:
            self._crear_glosa(db, valor_objetado=4200.0)
            nueva = self._crear_glosa(
                db,
                valor_objetado=20000.0,  # muy lejos del 10%
                estado="PENDIENTE",
                dictamen="",
            )
            r = _buscar_dictamen_gemelo(db, nueva, nueva.texto_glosa_original)
            assert r is None
        finally:
            db.close()

    def test_no_reusa_si_concepto_distinto(self):
        db = self._setup_db()
        try:
            self._crear_glosa(db, texto_glosa_original="CO0701 - MEDICAMENTO FUERA DEL POS")
            nueva = self._crear_glosa(
                db,
                texto_glosa_original="CO0701 - PROCEDIMIENTO NO PERTINENTE",
                estado="PENDIENTE",
                dictamen="",
            )
            r = _buscar_dictamen_gemelo(db, nueva, nueva.texto_glosa_original)
            assert r is None
        finally:
            db.close()

    def test_no_reusa_si_otra_eps(self):
        db = self._setup_db()
        try:
            self._crear_glosa(db, eps="FAMISANAR EPS")
            nueva = self._crear_glosa(db, eps="COOSALUD EPS", estado="PENDIENTE", dictamen="")
            r = _buscar_dictamen_gemelo(db, nueva, nueva.texto_glosa_original)
            assert r is None
        finally:
            db.close()

    def test_no_reusa_si_dictamen_es_placeholder(self):
        db = self._setup_db()
        try:
            self._crear_glosa(db, dictamen="PENDIENTE")  # demasiado corto
            nueva = self._crear_glosa(db, estado="PENDIENTE", dictamen="")
            r = _buscar_dictamen_gemelo(db, nueva, nueva.texto_glosa_original)
            assert r is None
        finally:
            db.close()


class TestFlagIASoloComplejas:
    def test_flag_off_por_default(self, monkeypatch):
        monkeypatch.delenv("IA_SOLO_COMPLEJAS", raising=False)
        import app.services.auto_responder_service as ars

        importlib.reload(ars)
        assert ars._IA_SOLO_COMPLEJAS is False

    def test_flag_on_con_var(self, monkeypatch):
        monkeypatch.setenv("IA_SOLO_COMPLEJAS", "1")
        import app.services.auto_responder_service as ars

        importlib.reload(ars)
        assert ars._IA_SOLO_COMPLEJAS is True

    def test_reusar_gemelos_default_on(self, monkeypatch):
        monkeypatch.delenv("AUTO_RESPONDER_REUSAR_GEMELOS", raising=False)
        import app.services.auto_responder_service as ars

        importlib.reload(ars)
        assert ars._AUTO_RESPONDER_REUSAR_GEMELOS is True


class TestExportHistorialUsaFormatoRadicable:
    """El export del historial usaba 22 columnas planas con el dictamen
    truncado a 800 chars (713/809 cortados a mitad de oración en el lote
    real del 12-jun-2026) — incompatible con la radicación ante la EPS.
    Ahora delega a `generar_excel_radicable_con_nombre` (PR #111): 12
    columnas canónicas, header verde institucional, una fila por
    concepto, fila TOTAL GLOSADO y hoja FUNDAMENTO JURÍDICO.
    """

    def test_endpoint_invoca_generar_excel_radicable(self):
        from pathlib import Path

        src = Path("app/api/routers/glosas.py").read_text()
        # El endpoint /exportar-xlsx debe llamar al generador radicable.
        assert "generar_excel_radicable_con_nombre" in src, (
            "el export del historial debe usar el generador radicable (PR #111)"
        )
        # Y no debe truncar el dictamen — lo emite completo el generador.
        assert "dictamen_txt[:800]" not in src, "el cap de 800 chars debe estar eliminado"
