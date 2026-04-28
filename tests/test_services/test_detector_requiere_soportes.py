"""Tests del detector REQUIERE_SOPORTES (gating gratis pre-IA)."""
from __future__ import annotations

from app.services.detector_requiere_soportes import evaluar, mensaje_para_dictamen


class TestEvaluar:
    def test_texto_muy_corto_requiere(self):
        r = evaluar(codigo_glosa="TA0201", texto_glosa="x")
        assert r["requiere"] is True
        assert r["puede_procesar_ia"] is False

    def test_placeholder_importacion_requiere(self):
        r = evaluar(
            codigo_glosa="TA0201",
            texto_glosa="Glosa importada desde recepción. Pendiente de análisis y respuesta por el gestor asignado.",
        )
        assert r["requiere"] is True
        assert "importada" in r["motivo"].lower() or "DGH" in r["motivo"]

    def test_so_sin_pdf_requiere(self):
        r = evaluar(
            codigo_glosa="SO0801",
            texto_glosa="SO0801 - Existe ausencia total parcial o inconsistencia en los soportes de cobro - CUPS 897011 - Valor objetado: $52.500",
            contexto_pdf="",
        )
        assert r["requiere"] is True
        assert "Soportes" in r["motivo"] or "soportes" in r["motivo"]
        assert any("Historia clínica" in s for s in r["soportes_sugeridos"])

    def test_so_con_pdf_grande_no_requiere(self):
        r = evaluar(
            codigo_glosa="SO0801",
            texto_glosa="SO0801 - Existe ausencia parcial - CUPS 897011 - Valor objetado: $52.500. Detalle adicional aquí ofreciendo contexto.",
            contexto_pdf="X" * 1500,
        )
        assert r["requiere"] is False

    def test_au_sin_autorizacion_requiere(self):
        r = evaluar(
            codigo_glosa="AU0101",
            texto_glosa="AU0101 - Falta autorización - CUPS 890101 - Valor objetado: $200.000",
            contexto_pdf="",
            numero_autorizacion=None,
        )
        assert r["requiere"] is True
        assert "Autorización" in r["motivo"] or "autorización" in r["motivo"]

    def test_au_con_autorizacion_no_requiere(self):
        r = evaluar(
            codigo_glosa="AU0101",
            texto_glosa="AU0101 - Falta autorización - CUPS 890101 - Valor objetado: $200.000",
            numero_autorizacion="AUT-12345",
        )
        assert r["requiere"] is False

    def test_pertinencia_clinica_sin_contexto(self):
        r = evaluar(
            codigo_glosa="CL0101",
            texto_glosa="CL0101 - Pertinencia clínica - CUPS 890101 - Valor objetado: $300.000",
            contexto_pdf="",
        )
        assert r["requiere"] is True
        assert "clínica" in r["motivo"].lower() or "tratante" in r["motivo"].lower()

    def test_alta_cuantia_sin_contexto_requiere(self):
        # Texto > 50 chars (no es regla de placeholder) pero corto y
        # valor alto → debería disparar alta cuantía.
        r = evaluar(
            codigo_glosa="TA0201",
            texto_glosa="TA0201 - tarifa - el cargo presenta diferencia con valores pactados",
            contexto_pdf="",
            valor_objetado=5_000_000.0,
        )
        assert r["requiere"] is True

    def test_caso_simple_no_requiere(self):
        r = evaluar(
            codigo_glosa="TA0201",
            texto_glosa="TA0201 - El cargo por consulta presenta diferencias con valores pactados - CUPS 890750 - Valor objetado: $24.900",
            contexto_pdf="",
            valor_objetado=24_900.0,
        )
        assert r["requiere"] is False
        assert r["puede_procesar_ia"] is True


class TestMensaje:
    def test_mensaje_vacio_si_no_requiere(self):
        r = {"requiere": False}
        assert mensaje_para_dictamen(r) == ""

    def test_mensaje_con_soportes_legible(self):
        r = evaluar(
            codigo_glosa="SO0801",
            texto_glosa="SO0801 - inconsistencia soportes - $50.000",
            contexto_pdf="",
        )
        msg = mensaje_para_dictamen(r, "SO0801")
        assert "REQUIERE SOPORTES" in msg
        assert "SO0801" in msg
        assert "Re-analizar" in msg
