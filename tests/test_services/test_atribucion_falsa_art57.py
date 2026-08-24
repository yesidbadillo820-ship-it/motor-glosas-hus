"""No se le puede atribuir a un artículo real algo que no dice (GL-190/192/195).

QUÉ PASÓ. La auditoría independiente de nueve dictámenes encontró que el
Art. 57 de la Ley 1438 de 2011 se citó en tres expedientes con TRES contenidos
distintos, y ninguno es el suyo:

  · GL-190 — «las decisiones de facturación son definitivas y no admiten
    recurso alguno»
  · GL-192 — «la carga de la prueba corresponde a la entidad que impone la glosa»
  · GL-195 — «la carga de la prueba recae en la entidad»

El Art. 57 real regula el trámite y los plazos de las glosas: 20 días hábiles
para glosar, 15 para responder, 10 para decidir. No dice una palabra ni de
firmeza de decisiones ni de carga de la prueba.

El auditor sospechó que el error venía de la base de conocimiento del sistema.
Se revisó: el Art. 57 guardado en el corpus es el correcto. La invención pasa
al redactar. Y las revisiones que ya existían solo miran lo que va ENTRE
COMILLAS — estas tres atribuciones iban parafraseadas, sin comillas, así que
los dictámenes salieron sellados como verificados.

QUÉ CUIDA ESTA PRUEBA. Que las tres frases reales se marquen, y —igual de
importante— que una cita correcta o una paráfrasis legítima NO se marquen: una
alarma en falso sobre un documento que se radica ante la EPS es peor que no
revisar, porque enseña al auditor a no creerle a las alarmas.
"""

import pytest

from app.services.citation_verifier import _lo_que_se_le_atribuye, verificar_citas


def _atribuciones(texto: str) -> list[dict]:
    reporte = verificar_citas(texto)
    return [i for i in reporte["issues"] if i["tipo"] == "ATRIBUCION_FALSA"]


class TestElCorpusNoTieneLaCulpa:
    def test_el_articulo_57_guardado_es_el_correcto(self):
        """Lo que el auditor pidió comprobar: si el error estaba en la base."""
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        art57 = _TODAS_LAS_NORMAS["LEY 1438 DE 2011"]["articulos"]["57"]
        texto = art57["texto"].lower()
        assert "glosa" in texto
        assert "20 días hábiles" in texto or "20 dias habiles" in texto
        # Lo que la IA le inventó NO está en el texto guardado:
        assert "carga de la prueba" not in texto
        assert "no admite recurso" not in texto


class TestLasTresFrasesDeLaAuditoria:
    def test_gl190_las_decisiones_son_definitivas(self):
        dictamen = (
            "SE RESPONDE CONFORME AL ARTÍCULO 57 DE LA LEY 1438 DE 2011, QUE "
            "ESTABLECE QUE LAS DECISIONES DE FACTURACIÓN SON DEFINITIVAS Y NO "
            "ADMITEN RECURSO ALGUNO."
        )
        hallazgos = _atribuciones(dictamen)
        assert hallazgos, "la atribución inventada de GL-190 pasó sin alarma"
        assert hallazgos[0]["severidad"] == "ALTA"
        assert "57" in hallazgos[0]["cita"]

    def test_gl192_la_carga_de_la_prueba_corresponde_a_la_entidad(self):
        dictamen = (
            "EN VIRTUD DEL ARTÍCULO 57 DE LA LEY 1438 DE 2011, QUE DISPONE QUE "
            "LA CARGA DE LA PRUEBA CORRESPONDE A LA ENTIDAD QUE IMPONE LA GLOSA."
        )
        hallazgos = _atribuciones(dictamen)
        assert hallazgos, "la atribución inventada de GL-192 pasó sin alarma"
        assert "carga de la prueba" in hallazgos[0]["detalle"]

    def test_gl195_con_la_norma_escrita_primero(self):
        """«La Ley 1438 de 2011, en su artículo 57, señala que...» — el mismo
        invento escrito al revés, que también tiene que caer."""
        dictamen = (
            "LA LEY 1438 DE 2011, EN SU ARTÍCULO 57, SEÑALA QUE LA CARGA DE LA "
            "PRUEBA RECAE EN LA ENTIDAD RESPONSABLE DEL PAGO."
        )
        assert _atribuciones(dictamen), "la atribución inventada de GL-195 pasó sin alarma"

    def test_el_hallazgo_le_dice_al_auditor_que_hacer(self):
        dictamen = (
            "EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 ESTABLECE QUE LA CARGA DE LA "
            "PRUEBA RECAE EN LA EPS."
        )
        h = _atribuciones(dictamen)[0]
        assert h["sugerencia"]
        assert "radicad" in h["sugerencia"].lower()

    def test_tambien_cuando_la_doctrina_va_dentro_de_un_inciso(self):
        dictamen = (
            "EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 ESTABLECE QUE, EN EL TRÁMITE "
            "DE GLOSAS, LA CARGA DE LA PRUEBA CORRESPONDE A LA EPS."
        )
        assert _atribuciones(dictamen)

    def test_no_se_repite_el_mismo_hallazgo_tres_veces(self):
        """El mismo invento dos veces en el mismo dictamen es UN problema."""
        dictamen = (
            "EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 ESTABLECE QUE LA CARGA DE LA "
            "PRUEBA RECAE EN LA EPS. ADEMÁS, EL ARTÍCULO 57 DE LA LEY 1438 DE "
            "2011 DISPONE QUE LA CARGA DE LA PRUEBA ES DE LA ENTIDAD."
        )
        assert len(_atribuciones(dictamen)) == 1


class TestLoQueNoSeDebeMarcar:
    """Una alarma en falso es peor que no revisar."""

    def test_la_cita_correcta_del_articulo_57_pasa_limpia(self):
        dictamen = (
            "EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 ESTABLECE QUE LA EPS TIENE 20 "
            "DÍAS HÁBILES PARA FORMULAR LA GLOSA Y EL PRESTADOR 15 PARA RESPONDERLA."
        )
        assert _atribuciones(dictamen) == []

    def test_parafrasear_sin_invocar_ninguna_doctrina_pasa_limpio(self):
        dictamen = (
            "CONFORME AL ARTÍCULO 57 DE LA LEY 1438 DE 2011, QUE REGULA EL TRÁMITE "
            "DE LAS GLOSAS, LA OBJECIÓN ES EXTEMPORÁNEA."
        )
        assert _atribuciones(dictamen) == []

    def test_la_doctrina_en_otra_clausula_no_es_una_atribucion(self):
        """Al artículo se le atribuye «el trámite y los plazos»; lo que sigue a
        la coma es una afirmación del redactor, no algo que diga el artículo."""
        dictamen = (
            "CONFORME AL ARTÍCULO 57 DE LA LEY 1438 DE 2011, QUE ESTABLECE EL "
            "TRÁMITE Y LOS PLAZOS DE LAS GLOSAS, LA CARGA DE LA PRUEBA DE LA "
            "OBJECIÓN CORRESPONDE A LA EPS."
        )
        assert _atribuciones(dictamen) == []

    def test_cuando_el_articulo_si_trata_la_doctrina_no_se_marca(self):
        """El Art. 168 de la Ley 100 sí habla de responsabilidad solidaria."""
        dictamen = (
            "EL ARTÍCULO 168 DE LA LEY 100 DE 1993 ESTABLECE LA RESPONSABILIDAD "
            "SOLIDARIA EN LA ATENCIÓN INICIAL DE URGENCIAS."
        )
        assert _atribuciones(dictamen) == []

    def test_un_articulo_que_no_esta_en_el_corpus_no_se_juzga(self):
        """Sin el texto real no se puede afirmar que algo «no está» ahí."""
        dictamen = (
            "EL ARTÍCULO 999 DE LA LEY 1438 DE 2011 ESTABLECE QUE LA CARGA DE LA "
            "PRUEBA RECAE EN LA EPS."
        )
        assert _atribuciones(dictamen) == []

    def test_un_dictamen_vacio_no_rompe_nada(self):
        assert _atribuciones("") == []


class TestElRecorteDeLaFrase:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("LA CARGA DE LA PRUEBA RECAE EN LA EPS", "LA CARGA DE LA PRUEBA RECAE EN LA EPS"),
            (
                "EL TRÁMITE DE GLOSAS, LA CARGA DE LA PRUEBA ES DE LA EPS",
                "EL TRÁMITE DE GLOSAS",
            ),
            # Abre con coma: es un inciso, y lo atribuido viene tras cerrarlo.
            (", EN LA GLOSA, LA CARGA ES DE LA EPS", "LA CARGA ES DE LA EPS"),
            # Inciso sin coma de cierre: se lee todo antes que perder la frase.
            (", EN LA GLOSA LA CARGA ES DE LA EPS", "EN LA GLOSA LA CARGA ES DE LA EPS"),
        ],
    )
    def test_se_queda_con_lo_que_de_verdad_se_atribuye(self, entrada, esperado):
        assert _lo_que_se_le_atribuye(entrada) == esperado


class TestNoSeBorranFrasesCorrectas:
    def test_el_limpiador_no_borra_por_atribucion_falsa(self):
        """El artículo SÍ existe: borrar todas sus frases se llevaría por
        delante las que están bien citadas en el mismo dictamen."""
        from app.services.dictamen_postprocesor import quitar_citas_invalidas_dinamico

        dictamen = (
            "EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 ESTABLECE QUE LA CARGA DE LA "
            "PRUEBA RECAE EN LA EPS. LA GLOSA SE FORMULÓ 34 DÍAS HÁBILES DESPUÉS "
            "DE LA RADICACIÓN, POR FUERA DE LOS 20 DÍAS DEL ARTÍCULO 57 DE LA LEY "
            "1438 DE 2011."
        )
        resultado = quitar_citas_invalidas_dinamico(dictamen)
        assert "34 DÍAS HÁBILES" in resultado, "se borró la frase que sí estaba bien"
