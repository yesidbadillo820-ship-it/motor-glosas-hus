"""No se afirma qué dice un documento que nadie adjuntó.

OT-005 · 05-08-2026. Prueba real en el motor del hospital, glosa AU0401 de
COMPENSAR, con la casilla de soportes vacía:

    "EL HISTORIAL MÉDICO DETALLA SÍNTOMAS DE DOLOR ABDOMINAL AGUDO QUE
     REQUIEREN IMÁGENES DE ALTA RESOLUCIÓN. EL INFORME DE RADIOLOGÍA INDICA
     LA NECESIDAD DE CONTRASTE PARA DESCARTAR PATOLOGÍAS GRAVES."

Nadie subió una historia clínica ni un informe de radiología. El motor
escribió lo que suele decir un caso así. Si la entidad pide ese informe, el
hospital queda afirmando algo que no puede probar — y eso pesa mucho más que
la glosa que se estaba discutiendo.

Cuando SÍ hay soportes la regla no aplica: ahí el motor los leyó.
"""

from __future__ import annotations

from app.services.glosa_service import _afirma_hechos_clinicos_sin_soporte as _afirma

DICTAMEN_COMPENSAR = (
    "ESE HUS NO ACEPTA LA GLOSA AU0401. EN PRIMER LUGAR, EL HISTORIAL MÉDICO "
    "DETALLA SÍNTOMAS DE DOLOR ABDOMINAL AGUDO QUE REQUIEREN IMÁGENES DE ALTA "
    "RESOLUCIÓN. EN SEGUNDO LUGAR, EL INFORME DE RADIOLOGÍA INDICA LA NECESIDAD "
    "DE CONTRASTE PARA DESCARTAR PATOLOGÍAS GRAVES."
)


class TestElCasoReal:
    def test_sin_soportes_se_avisa(self):
        assert _afirma(DICTAMEN_COMPENSAR, tiene_soportes=False) is True

    def test_con_soportes_no_se_avisa(self):
        """Si el auditor adjuntó los PDF, el motor los leyó: es legítimo."""
        assert _afirma(DICTAMEN_COMPENSAR, tiene_soportes=True) is False


class TestQueCuentaComoAfirmacion:
    def test_documentos_clinicos_con_verbo_de_contenido(self):
        for d in (
            "LA HISTORIA CLÍNICA REGISTRA LA ADMINISTRACIÓN DEL MEDICAMENTO",
            "LA EPICRISIS DESCRIBE LA EVOLUCIÓN FAVORABLE DEL PACIENTE",
            "EL REPORTE DE LABORATORIO EVIDENCIA LEUCOCITOSIS",
            "LA NOTA OPERATORIA CONSIGNA EL HALLAZGO INTRAOPERATORIO",
            "LA DESCRIPCIÓN QUIRÚRGICA DETALLA EL ABORDAJE UTILIZADO",
        ):
            assert _afirma(d, tiene_soportes=False) is True, d

    def test_dictamen_vacio(self):
        assert _afirma("", tiene_soportes=False) is False
        assert _afirma(None, tiene_soportes=False) is False


class TestLoQueNoDebeDisparar:
    def test_afirmacion_juridica_generica(self):
        """«La historia clínica constituye prueba plena» es derecho, no un
        hecho del paciente. No dice QUÉ contiene."""
        d = (
            "LA HISTORIA CLÍNICA INSTITUCIONAL, CONFORME A LA RESOLUCIÓN 1995/1999, "
            "CONSTITUYE PRUEBA PLENA Y ES EL ÚNICO DOCUMENTO EXIGIDO PARA VALIDAR "
            "LA PRESTACIÓN."
        )
        assert _afirma(d, tiene_soportes=False) is False

    def test_carga_de_la_prueba(self):
        d = (
            "LA CARGA PROBATORIA RECAE SOBRE LA ENTIDAD PAGADORA, QUE NO APORTÓ "
            "DOCUMENTO ALGUNO QUE SUSTENTE LA DISCREPANCIA."
        )
        assert _afirma(d, tiene_soportes=False) is False

    def test_dictamen_de_tarifas(self):
        d = (
            "EL VALOR FACTURADO CORRESPONDE A LA TARIFA PACTADA SOAT MENOS 5% "
            "SEGÚN EL ANEXO 3 DEL CONTRATO VIGENTE."
        )
        assert _afirma(d, tiene_soportes=False) is False

    def test_no_cruza_el_punto_final(self):
        """Dos frases distintas no se pegan: «...LA HISTORIA CLÍNICA. LA EPS
        INDICA...» no es una afirmación sobre la historia clínica."""
        d = "SE APORTA LA HISTORIA CLÍNICA. LA ENTIDAD INDICA QUE NO ES SUFICIENTE."
        assert _afirma(d, tiene_soportes=False) is False


class TestElAvisoEstaEnchufado:
    def test_el_dictamen_lo_agrega(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_afirma_hechos_clinicos_sin_soporte(dictamen, tiene_pdf)" in src
        i = src.index("_afirma_hechos_clinicos_sin_soporte(dictamen, tiene_pdf)")
        bloque = src[max(0, i - 600) : i + 1800]
        assert "NO SE ADJUNTARON" in bloque
        assert "CLINICA-SIN-SOPORTE" in bloque, "un fallo no puede tumbar el dictamen"
