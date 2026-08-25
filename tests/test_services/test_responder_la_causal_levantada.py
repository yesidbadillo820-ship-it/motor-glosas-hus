"""El dictamen tiene que contestar lo que la EPS objetó, no otra cosa.

QUÉ PASÓ. Las dos auditorías independientes encontraron el mismo defecto en
varios dictámenes: el motor contesta con un argumento correcto, pero de otro
tema.

  · GL-194 y GL-202 — la EPS glosó «precio superior al regulado» de un
    medicamento (Abiraterona) y el dictamen respondió sobre la validez formal
    de la factura electrónica y sobre la tarifa SOAT del contrato. Ni una vez
    tocó la regulación de precios, que era el punto.
  · GL-190 — la EPS pidió «se reliquida a manual ISS 2001» y el dictamen nunca
    dice por qué el ISS 2001 no aplica: solo reafirma que rige SOAT.
  · GL-195 y GL-199 — la EPS glosó por SOPORTES y el dictamen respondió sobre
    la validez formal de la factura, sin decir qué soporte falta ni por qué el
    que se anexó basta.

LA CAUSA. Existe un bloque que le dice al motor qué debe atacar punto por
punto, pero solo se emitía si alguno de sus patrones enganchaba. Ninguno cubría
«precio regulado» ni «reliquidar a otro manual», así que en esos casos el
bloque desaparecía entero y el motor se iba por lo genérico. Reproducido: con
los textos reales de los tres casos, el bloque salía con CERO caracteres.

QUÉ SE HIZO. Dos cosas. Se agregaron las dos causales que faltaban, con la
instrucción concreta de qué responder en cada una. Y —lo más importante— el
bloque ya nunca sale vacío: cuando ningún patrón engancha, se le pone delante
al motor el TEXTO LITERAL de la EPS con la orden de contestar eso. Los patrones
no pueden cubrir todas las formas de escribir una objeción; el texto de la EPS
siempre está.

Se cargaron además al corpus de verificación la Circular 19 y la Circular 18 de
2024, que son con las que se responde una glosa de precio regulado. Estaban en
la pantalla de Consulta Normativa pero no en el corpus, así que un dictamen que
las citara salía marcado en rojo como «norma inexistente».
"""

from app.services.analizador_motivo_eps import bloque_puntos_a_refutar, extraer_puntos_eps


def _bloque(texto: str) -> str:
    return bloque_puntos_a_refutar(extraer_puntos_eps(texto))


class TestLasTresCausalesQueSalianVacias:
    GL194 = (
        "EPS: DISPENSARIO MEDICO · FA1601 · Abiraterona 250 mg CUM 20146583-1 · "
        "$80.776 · Motivo: precio superior al regulado"
    )
    GL190 = "EPS: POSITIVA · TA5401 · CUPS 010101 · Motivo: se reliquida a manual ISS 2001"
    GL195 = "EPS: FOMAG · Código FA5701 · glosa por soportes"

    def test_precio_regulado_ya_no_sale_vacio(self):
        assert _bloque(self.GL194).strip(), "el bloque volvió a salir vacío"

    def test_precio_regulado_manda_atacar_la_regulacion_no_la_factura(self):
        bloque = _bloque(self.GL194)
        assert "Circular 19" in bloque
        assert "mercado relevante" in bloque.lower()
        assert "no la validez de la factura" in bloque.lower()

    def test_manual_alterno_ya_no_sale_vacio(self):
        assert _bloque(self.GL190).strip()

    def test_manual_alterno_exige_decir_por_que_no_aplica(self):
        bloque = _bloque(self.GL190).lower()
        assert "no basta con reafirmar" in bloque
        assert "por qué ese manual no aplica" in bloque

    def test_soportes_al_menos_recibe_el_texto_literal(self):
        bloque = _bloque(self.GL195)
        assert bloque.strip()
        assert "FA5701" in bloque or "soportes" in bloque.lower()


class TestElBloqueYaNuncaSeQuedaSinNada:
    def test_una_causal_rara_igual_trae_el_texto_de_la_eps(self):
        """Los patrones no pueden cubrir todas las formas de objetar."""
        texto = "EPS: NUEVA EPS · Motivo: el servicio no corresponde al episodio facturado"
        bloque = _bloque(texto)
        assert bloque.strip()
        assert "no corresponde al episodio facturado" in bloque

    def test_le_explica_al_motor_por_que_importa(self):
        bloque = _bloque("EPS: X · Motivo: algo raro que ningún patrón reconoce")
        assert "lo que no se contesta se da por aceptado" in bloque.lower()

    def test_sin_texto_no_se_inventa_un_bloque(self):
        assert _bloque("") == ""


class TestLasCircularesDePrecioRegulado:
    """Sin ellas en el corpus, el arreglo sería contraproducente."""

    def test_citarlas_ya_no_las_marca_como_inexistentes(self):
        from app.services.citation_verifier import verificar_citas

        dictamen = (
            "EL PRECIO FACTURADO SE AJUSTA A LA CIRCULAR 19 DE 2024 DEL CNPMDM, "
            "CUYO PARÁGRAFO 2 DEL ARTÍCULO 1 PERMITE ADICIONAR EL MARGEN DEL "
            "ARTÍCULO 11 DE LA CIRCULAR 18 DE 2024."
        )
        inexistentes = [
            i for i in verificar_citas(dictamen)["issues"] if i["tipo"] == "NORMA_INEXISTENTE"
        ]
        assert inexistentes == [], f"marcó como inexistente una circular real: {inexistentes}"

    def test_el_corpus_guarda_la_defensa_clave(self):
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        notas = _TODAS_LAS_NORMAS["CIRCULAR 19 DE 2024"]["notas"].lower()
        assert "mercado relevante" in notas
        assert "adicionar" in notas
