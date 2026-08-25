"""El Decreto 4747 tenia TRES articulos inventados en el corpus.

Segunda auditoria del lote del 25-08-2026. Un auditor independiente reviso
las mismas 117 respuestas y encontro que las 28 de ratificacion —el 100 %—
citaban el "ARTICULO 20 DEL DECRETO 4747 DE 2007" como si regulara el
tramite de glosas.

Se contrasto con el texto del decreto publicado por MinSalud. El auditor
tenia razon, y el problema era mas hondo: los TRES articulos que el corpus
tenia cargados de ese decreto estaban mal, con encabezado y texto inventados:

    Art. 11 decia "Atencion de urgencias"            -> es "Verificacion de
                                                        derechos de los usuarios"
    Art. 20 decia "Tramite de glosas - conciliacion" -> es "RIPS"
    Art. 21 decia "Pago durante tramite de glosas"   -> es "Soportes de las facturas"

El tramite de glosas es el Art. 23; el Manual Unico, el 22.

Lo grave no es la cita: es que se certificaba sola. El revisor de citas
contrasta contra ESTE corpus, asi que el dictamen salia sellado "verificado"
llevando una norma que dice otra cosa. Misma leccion de la jurisprudencia
del 24-08: un corpus sin verificar no verifica nada.
"""

from app.services.glosa_service import (
    TEXTO_RATIFICADA,
    _corregir_articulo_mal_citado,
)
from app.services.normativa_completa import _TODAS_LAS_NORMAS as NORMAS

ARTS = NORMAS["DECRETO 4747 DE 2007"]["articulos"]


class TestLosArticulosDicenLoQueDicen:
    def test_el_11_es_verificacion_de_derechos(self):
        assert "Verificación de derechos" in ARTS["11"]["titulo"]
        assert "Atención de urgencias" not in ARTS["11"]["titulo"]

    def test_el_20_es_el_del_rips(self):
        assert "RIPS" in ARTS["20"]["titulo"]
        assert "glosa" not in ARTS["20"]["titulo"].lower()

    def test_el_21_es_el_de_soportes(self):
        assert "Soportes de las facturas" in ARTS["21"]["titulo"]
        assert "no podrá exigir soportes adicionales" in ARTS["21"]["texto"]

    def test_el_22_es_el_del_manual_unico(self):
        assert "Manual único de glosas" in ARTS["22"]["titulo"]

    def test_el_23_es_el_del_tramite_de_glosas(self):
        assert ARTS["23"]["titulo"] == "Trámite de glosas"
        assert "quince (15) días hábiles" in ARTS["23"]["texto"]
        assert "diez (10) días hábiles" in ARTS["23"]["texto"]

    def test_el_23_avisa_que_la_ley_1438_le_cambio_el_plazo(self):
        """El decreto dice 30 dias habiles para formular la glosa; el Art. 57
        de la Ley 1438 de 2011 los bajo a VEINTE. Si el motor argumenta 30
        esta regalando diez dias."""
        assert "VEINTE" in ARTS["23"]["aplicacion"]
        assert "1438" in ARTS["23"]["aplicacion"]

    def test_el_23_trae_la_defensa_contra_la_causal_nueva(self):
        assert "hechos nuevos" in ARTS["23"]["texto"]

    def test_queda_constancia_de_contra_que_se_verifico(self):
        assert NORMAS["DECRETO 4747 DE 2007"]["verificada"]


class TestElTextoDeRatificacion:
    def test_cita_el_articulo_23_no_el_20(self):
        assert "ARTÍCULO 23 DEL DECRETO 4747 DE 2007" in TEXTO_RATIFICADA
        assert "ARTÍCULO 20 DEL DECRETO 4747" not in TEXTO_RATIFICADA

    def test_conserva_el_resto_de_lo_que_pidio_el_area(self):
        for pedazo in (
            "ARTÍCULO 57 DE LA LEY 1438 DE 2011",
            "SUPERINTENDENCIA NACIONAL DE SALUD",
            "CONCILIACIÓN DE AUDITORÍA MÉDICA",
        ):
            assert pedazo in TEXTO_RATIFICADA, pedazo


class TestLaRedQueCorrigeElArticulo:
    def test_corrige_cuando_el_tema_es_glosas(self):
        texto = "SE DA CONTINUACIÓN CONFORME AL ARTÍCULO 20 DEL DECRETO 4747 DE 2007 · GLOSA."
        salida = _corregir_articulo_mal_citado(texto)
        assert "ARTÍCULO 23 DEL DECRETO 4747" in salida

    def test_corrige_la_forma_abreviada(self):
        texto = "SE INVITA A MESA DE CONCILIACIÓN (ART. 20 DEC. 4747/2007) POR LA GLOSA."
        assert "ART. 23 DEC. 4747" in _corregir_articulo_mal_citado(texto)

    def test_no_toca_el_articulo_20_cuando_de_verdad_habla_de_rips(self):
        """El Art. 20 EXISTE y es el del RIPS: citarlo para RIPS esta bien."""
        texto = "LOS RIPS SE REPORTAN CONFORME AL ARTÍCULO 20 DEL DECRETO 4747 DE 2007."
        assert _corregir_articulo_mal_citado(texto) == texto

    def test_no_toca_la_cita_ya_correcta(self):
        texto = "EL ARTÍCULO 23 DEL DECRETO 4747 DE 2007 REGULA EL TRÁMITE DE LA GLOSA."
        assert _corregir_articulo_mal_citado(texto) == texto

    def test_no_toca_otros_decretos(self):
        texto = "EL ARTÍCULO 20 DEL DECRETO 780 DE 2016 Y LA GLOSA APLICADA."
        assert _corregir_articulo_mal_citado(texto) == texto

    def test_texto_vacio_no_rompe(self):
        assert _corregir_articulo_mal_citado("") == ""
        assert _corregir_articulo_mal_citado(None) is None
