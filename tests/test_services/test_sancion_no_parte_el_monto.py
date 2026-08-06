"""El rechazo de la sanción no puede partir el monto en dos.

OT-009 · 06-08-2026. Glosa de prueba de COOSALUD:

    "Se aplica sanción del 10% sobre el valor de la factura por
     incumplimiento en los tiempos de radicación, conforme a la cláusula 18
     del contrato. Valor descontado $1.750.000."

El rechazo por vicio de competencia funcionó —es el argumento correcto—,
pero se insertó "después del primer punto" y ese primer punto era el
separador de miles de $ 1.750.000. La casilla del VALOR OBJETADO del
dictamen entregado quedó así:

    $ 1. ADICIONALMENTE, EL HUS RECHAZA POR VICIO DE COMPETENCIA ... Art.
    21).750.000

Eso es lo que sale impreso en el documento que se radica ante la entidad.
"""

from __future__ import annotations

from app.services.glosa_service import _rechazar_sancion_eps_ilegal

GLOSA_SANCION = (
    "Se aplica sanción del 10% sobre el valor de la factura por incumplimiento "
    "en los tiempos de radicación, conforme a la cláusula 18 del contrato. "
    "Valor descontado $1.750.000."
)


class TestElMontoNoSeParte:
    def test_el_caso_real_coosalud(self):
        d = "ESE HUS NO ACEPTA LA GLOSA POR $ 1.750.000. LA AUDITORÍA NO TIENE RAZÓN."
        out = _rechazar_sancion_eps_ilegal(d, texto_glosa=GLOSA_SANCION)
        assert "$ 1.750.000" in out, "el monto quedó partido por el bloque inyectado"
        assert "$ 1. ADICIONALMENTE" not in out

    def test_el_monto_al_principio_del_dictamen(self):
        """El caso más duro: el monto es lo primero que aparece."""
        d = "$ 1.750.000 ES EL VALOR DESCONTADO POR LA ENTIDAD. SE RECHAZA."
        out = _rechazar_sancion_eps_ilegal(d, texto_glosa=GLOSA_SANCION)
        assert "$ 1.750.000" in out

    def test_no_se_mete_dentro_de_una_abreviatura(self):
        """"ART. 126" y "RES. 2284" también traen punto y no son fin de
        oración: el bloque no puede quedar en la mitad de la cita."""
        d = "ESE HUS INVOCA EL ART. 126 DE LA LEY 1438 DE 2011. LA GLOSA NO PROCEDE."
        out = _rechazar_sancion_eps_ilegal(d, texto_glosa=GLOSA_SANCION)
        assert "ART. 126" in out
        assert "ART. ADICIONALMENTE" not in out


class TestElArgumentoSigueSaliendo:
    def test_se_inyecta_el_rechazo_por_vicio_de_competencia(self):
        d = "ESE HUS NO ACEPTA LA GLOSA POR $ 1.750.000. LA AUDITORÍA NO TIENE RAZÓN."
        out = _rechazar_sancion_eps_ilegal(d, texto_glosa=GLOSA_SANCION)
        assert "VICIO DE COMPETENCIA" in out
        assert "SUPERINTENDENCIA NACIONAL DE SALUD" in out.upper()

    def test_queda_despues_de_la_primera_oracion_completa(self):
        d = "ESE HUS NO ACEPTA LA GLOSA POR $ 1.750.000. LA AUDITORÍA NO TIENE RAZÓN."
        out = _rechazar_sancion_eps_ilegal(d, texto_glosa=GLOSA_SANCION)
        assert out.startswith("ESE HUS NO ACEPTA LA GLOSA POR $ 1.750.000.")
        assert out.rstrip().endswith("LA AUDITORÍA NO TIENE RAZÓN.")

    def test_si_ya_lo_menciona_no_se_duplica(self):
        d = (
            "ESE HUS RECHAZA POR VICIO DE COMPETENCIA LA SANCIÓN DE $ 1.750.000. "
            "LA AUDITORÍA NO TIENE RAZÓN."
        )
        assert _rechazar_sancion_eps_ilegal(d, texto_glosa=GLOSA_SANCION) == d

    def test_glosa_sin_sancion_no_se_toca(self):
        d = "ESE HUS NO ACEPTA LA GLOSA POR $ 1.750.000. LA AUDITORÍA NO TIENE RAZÓN."
        assert _rechazar_sancion_eps_ilegal(d, texto_glosa="SO0201 FALTA EPICRISIS") == d

    def test_sin_texto_de_glosa_no_se_toca(self):
        d = "ESE HUS NO ACEPTA LA GLOSA POR $ 1.750.000."
        assert _rechazar_sancion_eps_ilegal(d, texto_glosa=None) == d
        assert _rechazar_sancion_eps_ilegal("", texto_glosa=GLOSA_SANCION) == ""
