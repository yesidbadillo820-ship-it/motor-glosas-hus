"""El motor le estaba borrando al dictamen artículos que sí existen.

QUÉ PASÓ (24-08-2026). Revisando por qué el dictamen GL-207 citaba el Art. 87
del Decreto 2423 de 1996 sin que el sistema pudiera respaldarlo, aparecieron dos
defectos que se tapaban el uno al otro.

PRIMERO — «DEL DECRETO» no se reconocía. El sistema aceptaba «del artículo 87 DE
LA Ley…» y «DE Ley…», pero no la contracción «DEL», que es como se escribe
normalmente en español. Con esa forma solo capturaba el número del artículo y
dejaba la norma en blanco, así que la cita no se revisaba contra nada.

SEGUNDO — y este es el grave. Cuando sí reconocía la norma, el sistema afirmaba
«esta norma no contiene ese artículo» con solo mirar los artículos que tiene
cargados. Y tiene muy pocos: de 131 normas, apenas 26 traen algún artículo, y la
que más tiene, cuatro. De la Ley 100 de 1993 están cargados el 168, el 177 y el
178 — tres de casi trescientos.

Peor todavía: el limpiador de dictámenes borra la ORACIÓN ENTERA que menciona
una cita marcada así. Reproducido ese día: un dictamen que citaba el Art. 156 de
la Ley 100 —artículo real, de los cimientos del sistema— salía sin esa frase. El
motor le estaba quitando al documento que se radica ante la EPS un argumento
correcto, sin decírselo a nadie.

QUÉ SE HIZO. Que un artículo no esté en el corpus no prueba que no exista. Ahora
el sistema solo afirma que el artículo no existe cuando de esa norma se cargó la
lista COMPLETA de artículos. Si la lista es parcial, avisa con severidad baja y
sin borrar nada: «no se pudo verificar, revíselo a mano».

Y el Art. 87 del Decreto 2423 se agregó al corpus con su texto oficial, porque
resultó que la cita del GL-207 era CORRECTA — lo que fallaba era que el sistema
no la tenía con qué respaldar.
"""

from app.services.citation_verifier import verificar_citas
from app.services.dictamen_postprocesor import quitar_citas_invalidas_dinamico


def _tipos(texto: str) -> list[str]:
    return [i["tipo"] for i in verificar_citas(texto)["issues"]]


class TestNoSeBorraUnArticuloQueSiExiste:
    FRASE_REAL = (
        "EL ARTÍCULO 156 DE LA LEY 100 DE 1993 ESTABLECE LAS CARACTERÍSTICAS BÁSICAS "
        "DEL SISTEMA GENERAL DE SEGURIDAD SOCIAL EN SALUD."
    )

    def test_el_articulo_156_sigue_en_el_dictamen(self):
        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA. " + self.FRASE_REAL + " SE SOLICITA EL LEVANTAMIENTO."
        )
        resultado = quitar_citas_invalidas_dinamico(dictamen)
        assert "156" in resultado, "se volvió a borrar un artículo real del dictamen"

    def test_se_avisa_pero_sin_acusar(self):
        """El auditor merece saber que no se pudo comprobar; eso no es lo mismo
        que decirle que el artículo no existe."""
        tipos = _tipos(self.FRASE_REAL)
        assert "ARTICULO_FUERA_DE_NORMA" not in tipos
        assert "ARTICULO_NO_VERIFICABLE" in tipos

    def test_el_aviso_es_de_severidad_baja(self):
        hallazgos = [
            i
            for i in verificar_citas(self.FRASE_REAL)["issues"]
            if i["tipo"] == "ARTICULO_NO_VERIFICABLE"
        ]
        assert hallazgos and hallazgos[0]["severidad"] == "BAJA"

    def test_el_aviso_dice_cuantos_articulos_hay_cargados(self):
        hallazgo = [
            i
            for i in verificar_citas(self.FRASE_REAL)["issues"]
            if i["tipo"] == "ARTICULO_NO_VERIFICABLE"
        ][0]
        assert "3 artículo" in hallazgo["detalle"], hallazgo["detalle"]


class TestSiLaListaEstaCompletaSiSeAcusa:
    def test_una_norma_marcada_completa_si_delata_el_numero_malo(self, monkeypatch):
        """La revisión no se apagó: donde se puede afirmar, se afirma."""
        import app.services.normativa_completa as nc

        norma = nc._TODAS_LAS_NORMAS["LEY 100 DE 1993"]
        monkeypatch.setitem(norma, "articulos_completos", True)
        tipos = _tipos("EL ARTÍCULO 9999 DE LA LEY 100 DE 1993 DICE ALGO.")
        assert "ARTICULO_FUERA_DE_NORMA" in tipos


class TestSeReconoceLaContraccionDel:
    def test_del_decreto_ahora_se_lee(self):
        from app.services.citation_verifier import PAT_ARTICULO

        m = PAT_ARTICULO.search("EL ARTÍCULO 87 DEL DECRETO 2423 DE 1996 RIGE.")
        assert m and m.groups() == ("87", "DECRETO", "2423", "1996")

    def test_el_anio_con_barra_tambien(self):
        from app.services.citation_verifier import PAT_ARTICULO

        m = PAT_ARTICULO.search("EL ARTÍCULO 87 DEL DECRETO 2423/1996 RIGE.")
        assert m and m.groups() == ("87", "DECRETO", "2423", "1996")

    def test_sigue_leyendo_las_formas_de_antes(self):
        from app.services.citation_verifier import PAT_ARTICULO

        m = PAT_ARTICULO.search("EL ARTÍCULO 3 DE LA RESOLUCIÓN 1995 DE 1999 RIGE.")
        assert m and m.groups()[0] == "3"
        assert m.groups()[2:] == ("1995", "1999")


class TestElArticulo87DelDecreto2423:
    """La cita del GL-207 era correcta; lo que faltaba era el respaldo."""

    def test_esta_en_el_corpus_con_su_texto_oficial(self):
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        art = _TODAS_LAS_NORMAS["DECRETO 2423 DE 1996"]["articulos"]["87"]
        texto = art["texto"].lower()
        assert "circunstancias de orden tecnológico" in texto
        assert "no tenga asignada tarifa" in texto
        assert "tarifa que tenga definida la institución" in texto
        # El artículo exige la comprobación del médico tratante: sin eso el
        # argumento queda cojo, y el corpus debe recordarlo.
        assert "comprobación del médico tratante" in texto

    def test_citarlo_ya_no_deja_hallazgos(self):
        dictamen = (
            "EN AUSENCIA DE TARIFA PACTADA, EL VALOR FACTURADO TIENE FUNDAMENTO EN EL "
            "ARTÍCULO 87 DEL DECRETO 2423 DE 1996."
        )
        assert _tipos(dictamen) == []

    def test_la_cita_literal_del_gl207_se_reconoce_como_verdadera(self):
        dictamen = (
            "EL ARTÍCULO 87 DEL DECRETO 2423 DE 1996 ESTABLECE QUE «POR LAS CIRCUNSTANCIAS "
            "DE ORDEN TECNOLÓGICO, CUANDO ALGUNA INSTITUCIÓN PRESTADORA DE SERVICIOS DE "
            "SALUD REALICE UN PROCEDIMIENTO QUE NO SE ENCUENTRE DEFINIDO Y POR LO TANTO NO "
            "TENGA ASIGNADA TARIFA, ÉSTE SE RECONOCERÁ POR LA TARIFA QUE TENGA DEFINIDA LA "
            "INSTITUCIÓN»."
        )
        falsas = [i for i in verificar_citas(dictamen)["issues"] if "FALSA" in i["tipo"]]
        assert falsas == [], f"se marcó como falsa una cita literal verdadera: {falsas}"
