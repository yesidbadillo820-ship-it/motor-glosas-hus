"""El dictamen se radica en MAYÚSCULAS. Lo decide el sistema, no el modelo.

05-08-2026, prueba real con seis glosas difíciles: unos dictámenes salieron
enteros en mayúscula y otros en minúscula («ESE HUS no acepta la glosa…»),
según lo que hubiera decidido el modelo esa vez. Y con el texto en
minúsculas aparecía «En ESE orden de ideas»: «ESE» es la sigla del hospital
(Empresa Social del Estado), quedaba en mayúscula sola en medio de la frase
y parecía un error de tipeo en un documento que sale a la EPS.
"""

from __future__ import annotations

from app.services.glosa_service import a_mayusculas_html


class TestPasarAMayusculas:
    def test_el_texto_sube_completo(self):
        assert a_mayusculas_html("ESE HUS no acepta la glosa") == "ESE HUS NO ACEPTA LA GLOSA"

    def test_las_tildes_y_la_enie_suben_bien(self):
        assert a_mayusculas_html("año, cláusula, señor") == "AÑO, CLÁUSULA, SEÑOR"

    def test_no_toca_las_etiquetas_html(self):
        html = '<div style="color:#1e3a8a">no acepta</div>'
        assert a_mayusculas_html(html) == '<div style="color:#1e3a8a">NO ACEPTA</div>'

    def test_no_rompe_las_entidades(self):
        assert a_mayusculas_html("uno&nbsp;dos") == "UNO&nbsp;DOS"

    def test_desaparece_el_ese_orden_de_ideas(self):
        """El defecto tal cual salía en el dictamen del 05-08."""
        salida = a_mayusculas_html("En ESE orden de ideas, se solicita el levantamiento")
        assert "En ESE orden" not in salida
        assert salida.startswith("EN ESE ORDEN DE IDEAS")

    def test_vacio_o_nulo_no_revienta(self):
        assert a_mayusculas_html("") == ""
        assert a_mayusculas_html(None) is None


class TestElDictamenSaleEnMayusculas:
    def _servicio(self):
        from app.services.glosa_service import GlosaService

        return GlosaService(groq_api_key="gsk_x")

    def _argumento(self, texto):
        # Por encima de MIN_CHARS_ARGUMENTO para pasar la guarda de vacío.
        return texto + " " + ("relleno jurídico suficiente para la guarda. " * 4)

    def test_la_argumentacion_sube_aunque_el_modelo_la_escriba_en_minuscula(self):
        html = self._servicio()._generar_dictamen_html(
            codigo="TA0801",
            valor="$ 4.860.000",
            cod_res="RE9901",
            desc_res="GLOSA NO ACEPTADA",
            argumento=self._argumento("ESE HUS no acepta la glosa por concepto de tarifas"),
            eps="FAMISANAR EPS",
            tipo="TA_TARIFA",
        )
        assert "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE TARIFAS" in html
        assert "no acepta la glosa" not in html

    def test_tambien_suben_servicio_contrato_tarifa_y_normas(self):
        html = self._servicio()._generar_dictamen_html(
            codigo="TA0801",
            valor="$ 1.000.000",
            cod_res="RE9901",
            desc_res="GLOSA NO ACEPTADA",
            argumento=self._argumento("texto del argumento"),
            eps="NUEVA EPS",
            tipo="TA_TARIFA",
            servicio="Procedimiento de consulta",
            contrato="Contrato 440 de 2025",
            tarifa="SOAT pleno",
            normas_clave="Ley 1438/2011 Art. 57|Resolución 2284 de 2023",
        )
        assert "PROCEDIMIENTO DE CONSULTA" in html
        assert "CONTRATO 440 DE 2025" in html
        assert "SOAT PLENO" in html
        assert "RESOLUCIÓN 2284 DE 2023" in html

    def test_el_html_sigue_siendo_html(self):
        """Subir a mayúsculas no puede romper la carátula."""
        html = self._servicio()._generar_dictamen_html(
            codigo="SO0201",
            valor="$ 890.000",
            cod_res="RE9901",
            desc_res="GLOSA NO ACEPTADA",
            argumento=self._argumento("<b>ESE HUS</b> no acepta la <i>glosa</i>"),
            eps="NUEVA EPS",
            tipo="SO_SOPORTES",
        )
        assert "<b>ESE HUS</b>" in html
        assert "<i>GLOSA</i>" in html
        assert "<B>" not in html  # la etiqueta no se toca
