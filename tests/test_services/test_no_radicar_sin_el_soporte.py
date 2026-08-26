"""Un dictamen que argumenta pero no prueba no deberia radicarse.

Del lote del 25-08: NUEVE de cada diez dictamenes afirmaban cosas de la
historia clinica sin que hubiera un solo soporte anexo. El motor avisaba, pero
con un aviso generico —«no se encontro el expediente»— que no decia QUE faltaba
ni por que importaba en ESE caso. Por eso se ignoraba.

Decision del area (26-08): que no deje radicar sin el soporte de la causal.

La regla es la del sentido comun del auditor: una glosa SO0101 dice que la
epicrisis no soporta la estancia. Sin epicrisis no hay respuesta que valga, por
bien redactada que este. Una AU0202 se prueba con la autorizacion o con la
historia que la registra. Una TA con la factura.
"""

from app.services.catalogo_glosas import SOPORTE_QUE_PIDE_LA_CAUSAL, soportes_que_pide
from app.services.glosa_service import _resaltar_avisos


class TestQueSoportePideCadaCausal:
    def test_la_glosa_de_soportes_pide_el_soporte(self):
        assert "epicrisis" in soportes_que_pide("SO0101")

    def test_la_de_autorizacion_se_prueba_con_la_historia(self):
        pedidos = soportes_que_pide("AU0202")
        assert "historia_clinica" in pedidos

    def test_la_de_pertinencia_tambien(self):
        """La decisión clínica vive en la historia: es donde se prueba."""
        assert "historia_clinica" in soportes_que_pide("CL0801")

    def test_los_medicamentos_con_la_hoja_de_administracion(self):
        assert "hoja_administracion_medicamentos" in soportes_que_pide("ME0101")

    def test_busca_primero_el_codigo_y_luego_la_familia(self):
        """SO0101 tiene regla propia; SO4101 cae en la de la familia SO."""
        assert soportes_que_pide("SO0101") == SOPORTE_QUE_PIDE_LA_CAUSAL["SO01"]
        assert soportes_que_pide("SO9999") == SOPORTE_QUE_PIDE_LA_CAUSAL["SO"]

    def test_un_codigo_desconocido_no_inventa_un_requisito(self):
        """No se le puede exigir al gestor un soporte que la norma no pide."""
        assert soportes_que_pide("XX9999") == ()
        assert soportes_que_pide("") == ()
        assert soportes_que_pide(None) == ()


class TestElAvisoSeVeEnPapel:
    """El dictamen se radica impreso. Un aviso de «no radicar» que sale como un
    renglón más de texto no detiene a nadie."""

    def test_envuelve_el_aviso_de_no_radicar(self):
        html = _resaltar_avisos(
            "ESE HUS NO ACEPTA LA GLOSA. ⛔ NO RADICAR TODAVÍA: falta la epicrisis."
        )
        assert "aviso-no-radicar" in html

    def test_envuelve_tambien_el_de_revisar(self):
        html = _resaltar_avisos(
            "TEXTO. ⚠ REVISAR ANTES DE RADICAR: la glosa no discute la factura."
        )
        assert "aviso-no-radicar" in html

    def test_el_color_sobrevive_a_la_impresora(self):
        html = _resaltar_avisos("⛔ NO RADICAR TODAVÍA: falta la historia clínica.")
        assert "print-color-adjust" in html

    def test_no_toca_un_dictamen_sin_avisos(self):
        limpio = "ESE HUS NO ACEPTA LA GLOSA. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        assert _resaltar_avisos(limpio) == limpio

    def test_texto_vacio_no_rompe(self):
        assert _resaltar_avisos("") == ""
        assert _resaltar_avisos(None) is None
