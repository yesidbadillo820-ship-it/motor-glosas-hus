"""Una pregunta clínica no se contesta con la tabla de tarifas.

OT-003 · 05-08-2026. Glosa de prueba TA0601 de PPL:

    "TAC DE ABDOMEN NO PERTINENTE PARA EL DIAGNÓSTICO REGISTRADO"

El código empieza por TA, así que el motor entregó el texto fijo de tarifas
—SOAT, UVB, valores pactados— a una pregunta que era clínica. Respondió otra
cosa, y una glosa que no se contesta se ratifica.

La causal tampoco calza con el hecho: TA0601 del catálogo es "dispositivos
médicos: diferencias con valores pactados". Eso es aplicación indebida de
causal y juega a favor del hospital, pero solo si el dictamen lo dice — y
para decirlo hay que pasar por el motor, no por el texto fijo.

Mismo remedio que se aplicó ese día al texto fijo del Dispensario: el texto
canónico sigue, pero solo cuando el tema calce.
"""

from __future__ import annotations

from app.services.glosa_service import _glosa_es_de_pertinencia

GLOSA_PPL = "TA0601 — TAC DE ABDOMEN NO PERTINENTE PARA EL DIAGNÓSTICO REGISTRADO."


class TestSeReconoceElMotivoClinico:
    def test_el_caso_real_ppl(self):
        assert _glosa_es_de_pertinencia(GLOSA_PPL) is True

    def test_sin_tildes_tambien(self):
        """La EPS escribe «DIAGNOSTICO» o «DIAGNÓSTICO» según quién redacte."""
        assert _glosa_es_de_pertinencia("EL EXAMEN NO CORRESPONDE AL DIAGNOSTICO") is True
        assert _glosa_es_de_pertinencia("EL EXAMEN NO CORRESPONDE AL DIAGNÓSTICO") is True

    def test_otras_formas_de_decirlo(self):
        for t in (
            "PROCEDIMIENTO SIN JUSTIFICACIÓN CLÍNICA",
            "SIN INDICACIÓN MÉDICA PARA EL SERVICIO",
            "FALTA DE PERTINENCIA MÉDICA",
            "EL INSUMO NO ERA NECESARIO PARA LA ATENCIÓN",
            "NO GUARDA RELACIÓN CON EL DIAGNÓSTICO",
        ):
            assert _glosa_es_de_pertinencia(t) is True, t


class TestUnaGlosaDeTarifaSigueSiendoDeTarifa:
    def test_tarifa_pura(self):
        assert (
            _glosa_es_de_pertinencia("TA0801 — TARIFA SUPERIOR A LA PACTADA. SOAT UVB -5%.")
            is False
        )

    def test_valores_pactados(self):
        assert (
            _glosa_es_de_pertinencia("DIFERENCIA CON LOS VALORES PACTADOS EN EL ANEXO 3") is False
        )

    def test_texto_vacio(self):
        assert _glosa_es_de_pertinencia("") is False
        assert _glosa_es_de_pertinencia(None) is False


class TestElTextoFijoDeTarifasSeApartaX:
    def test_la_condicion_incluye_la_guarda(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        i = src.index('tipo_glosa = "TA_TARIFA"')
        bloque = src[max(0, i - 1500) : i]
        assert "_glosa_es_de_pertinencia(texto_base)" in bloque
        assert "not _glosa_es_de_pertinencia" in bloque

    def test_las_demas_condiciones_siguen_intactas(self):
        """No se cerró de más: el texto fijo sigue exigiendo lo mismo que
        antes, solo se le sumó la guarda."""
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        i = src.index('tipo_glosa = "TA_TARIFA"')
        bloque = src[max(0, i - 1500) : i]
        assert "es_tarifa" in bloque
        assert "not tiene_contrato" in bloque
        assert "not _es_dispensario_medico(eps_key)" in bloque
