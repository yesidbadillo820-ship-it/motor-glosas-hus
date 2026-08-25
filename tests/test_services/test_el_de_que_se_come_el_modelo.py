"""El «de» que falta en la frase que firma el auditor.

Lote de recepcion del 25-08-2026, 117 dictamenes. Once salieron sin la
preposicion en formulas donde el espanol no admite otra cosa:

    "SE SOLICITA EL LEVANTAMIENTO LA GLOSA"          (7 veces)
    "EL ARTICULO 17 LA LEY 1751 DE 2015"             (4 veces)
    "LA AUTONOMIA DE LOS PROFESIONALES LA SALUD"     (dentro de comillas)

El tercero es el peor: esta DENTRO de una cita textual del articulo 17 de la
Ley 1751, asi que el hospital le atribuye a la ley una frase mal transcrita
y la entidad la compara contra el texto oficial.

Se probo cada patron del modulo contra la frase bien escrita: ninguna de las
redes se come el "de". Lo escribe asi el modelo.
"""

from app.services.glosa_service import _reponer_preposicion_comida


class TestReponeElDe:
    def test_levantamiento_de_la_glosa(self):
        salida = _reponer_preposicion_comida("SE SOLICITA EL LEVANTAMIENTO LA GLOSA.")
        assert salida == "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."

    def test_levantamiento_en_plural_y_masculino(self):
        assert "LEVANTAMIENTO DE LOS" in _reponer_preposicion_comida("EL LEVANTAMIENTO LOS CARGOS")
        assert "LEVANTAMIENTO DE EL" in _reponer_preposicion_comida("EL LEVANTAMIENTO EL CARGO")

    def test_articulo_de_la_ley(self):
        salida = _reponer_preposicion_comida(
            "GARANTIZADA POR EL ARTÍCULO 17 LA LEY ESTATUTARIA 1751 DE 2015."
        )
        assert "ARTÍCULO 17 DE LA LEY ESTATUTARIA 1751" in salida

    def test_articulo_abreviado(self):
        assert "ART. 15 DE LA LEY" in _reponer_preposicion_comida("SEGÚN EL ART. 15 LA LEY 1751.")

    def test_profesionales_de_la_salud_dentro_de_la_cita(self):
        salida = _reponer_preposicion_comida(
            'EL ARTÍCULO 17 DICE: "SE GARANTIZA LA AUTONOMÍA DE LOS PROFESIONALES LA SALUD".'
        )
        assert "PROFESIONALES DE LA SALUD" in salida

    def test_respeta_la_caja_del_parrafo(self):
        assert _reponer_preposicion_comida("se solicita el levantamiento la glosa.") == (
            "se solicita el levantamiento de la glosa."
        )

    def test_repara_varias_en_el_mismo_dictamen(self):
        texto = (
            "EL ARTÍCULO 17 LA LEY 1751 GARANTIZA LA AUTONOMÍA DE LOS "
            "PROFESIONALES LA SALUD. SE SOLICITA EL LEVANTAMIENTO LA GLOSA."
        )
        salida = _reponer_preposicion_comida(texto)
        assert "ARTÍCULO 17 DE LA LEY" in salida
        assert "PROFESIONALES DE LA SALUD" in salida
        assert "LEVANTAMIENTO DE LA GLOSA" in salida


class TestNoTocaLoQueEstaBien:
    def test_la_frase_correcta_sale_identica(self):
        texto = (
            "EL ARTÍCULO 17 DE LA LEY 1751 DE 2015 GARANTIZA LA AUTONOMÍA DE LOS "
            "PROFESIONALES DE LA SALUD. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        )
        assert _reponer_preposicion_comida(texto) == texto

    def test_no_es_un_corrector_de_gramatica_general(self):
        """Estas estan BIEN escritas y aparecen en el lote. Si la red las
        tocara, estaria danando texto correcto."""
        for texto in (
            "SE SOLICITA EL LEVANTAMIENTO ÍNTEGRO DE LA GLOSA.",
            "HA OPERADO DE PLENO DERECHO EL FENÓMENO JURÍDICO DE LA ACEPTACIÓN TÁCITA.",
            "HA PRECLUIDO DEFINITIVAMENTE LA OPORTUNIDAD LEGAL DE LA EPS.",
            "ESE HUS NO ACEPTA LA GLOSA APLICADA BAJO EL CÓDIGO TA0201.",
        ):
            assert _reponer_preposicion_comida(texto) == texto, texto

    def test_no_duplica_el_de_si_ya_esta(self):
        texto = "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        assert _reponer_preposicion_comida(texto).count("DE LA GLOSA") == 1
        assert "DE DE" not in _reponer_preposicion_comida(texto)

    def test_texto_vacio_no_rompe(self):
        assert _reponer_preposicion_comida("") == ""
        assert _reponer_preposicion_comida(None) is None
