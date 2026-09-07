"""Ningun articulo del corpus puede quedar sin contrastar contra la fuente.

LO QUE PASO ESTA SEMANA. Tres auditorias independientes destaparon que el
motor citaba articulos con el epigrafe y el texto inventados — y que, como el
revisor de citas contrasta contra ese mismo corpus, las citas falsas se
autocertificaban: el dictamen salia sellado «citas verificadas · 0 hallazgos»
llevando una norma que dice otra cosa.

EL TAMANO REAL DEL PROBLEMA. Se repasaron las 26 normas del corpus que
guardan texto de articulo, contra el normograma de la SuperSalud, el Senado de
la Republica, funcionpublica y los PDF oficiales de MinSalud:

  · De las 6 primeras (las de uso diario), CINCO tenian algo inventado.
  · De los 20 articulos de las 16 restantes, LOS 20 estaban mal — 13 con
    epigrafe y texto falsos, 3 con el texto cambiado, 2 con el epigrafe
    cambiado y 2 que no existen en la norma que se les atribuia.
  · Ninguno de los 20 se cayo al intentar refutarlo.

Ejemplos de lo que decia el corpus:
  · Decreto 1082 art. 2.5.3.4.1.4.4 «Contratacion de prestadores de servicios
    de salud» — es «Convenios o contratos interadministrativos», y su texto
    sale del Decreto 1510 de 2013.
  · Decreto 1795 art. 6 «Cobertura» — es «Principios y caracteristicas».
  · Resolucion 4886 de 2018 art. 25 — esa resolucion adopta la Politica
    Nacional de Salud Mental y no tiene ese articulo.

ESTA PRUEBA es la que impide que vuelva a pasar: si alguien agrega un articulo
con su texto y no deja constancia de contra que lo verifico, se pone roja.
"""

from app.services.normativa_completa import _TODAS_LAS_NORMAS as NORMAS


def _con_texto_de_articulo():
    """Normas que guardan el TEXTO de algún artículo — las que se pueden citar
    entre comillas, y por tanto las que hay que haber verificado."""
    salida = {}
    for clave, norma in NORMAS.items():
        arts = {
            a: d
            for a, d in (norma.get("articulos") or {}).items()
            if isinstance(d, dict) and d.get("texto")
        }
        if arts:
            salida[clave] = (norma, arts)
    return salida


class TestNadieCitaSinHaberVerificado:
    def test_toda_norma_con_texto_de_articulo_deja_constancia(self):
        sin_constancia = [
            c for c, (n, _) in _con_texto_de_articulo().items() if not n.get("verificada")
        ]
        assert not sin_constancia, (
            "estas normas guardan el texto de un artículo y nadie dejó dicho contra qué "
            f"fuente se verificó: {sorted(sin_constancia)}. "
            "Un corpus sin verificar no verifica nada — es lo que destapó la auditoría "
            "del 25 y 26 de agosto de 2026."
        )

    def test_la_constancia_dice_contra_que_se_verifico(self):
        """«verificada: sí» no sirve: tiene que decir contra qué fuente."""
        pobres = []
        for clave, (norma, _) in _con_texto_de_articulo().items():
            v = str(norma.get("verificada") or "")
            if len(v) < 20:
                pobres.append(f"{clave}: «{v}»")
        assert not pobres, f"constancia sin fuente: {pobres}"

    def test_hay_corpus_de_verdad_que_vigilar(self):
        """Si alguien vacía el corpus, las pruebas de arriba pasarían solas."""
        con_texto = _con_texto_de_articulo()
        assert len(con_texto) >= 20, f"solo {len(con_texto)} normas con texto de artículo"
        total_arts = sum(len(a) for _, a in con_texto.values())
        assert total_arts >= 40, f"solo {total_arts} artículos con texto"


class TestLasQueMasSeCitan:
    """Las de uso diario, con el dato que el motor de verdad usa."""

    def test_el_articulo_57_lleva_sus_plazos_dentro_del_texto(self):
        t = NORMAS["LEY 1438 DE 2011"]["articulos"]["57"]["texto"]
        for n in ("veinte (20)", "quince (15)", "diez (10)"):
            assert n in t, n

    def test_el_tramite_de_glosas_del_4747_es_el_articulo_23(self):
        assert NORMAS["DECRETO 4747 DE 2007"]["articulos"]["23"]["titulo"] == "Trámite de glosas"

    def test_el_168_de_la_ley_100_sigue_siendo_el_de_urgencias(self):
        t = NORMAS["LEY 100 DE 1993"]["articulos"]["168"]
        assert t["titulo"] == "Atención inicial de urgencias"
        assert "no requiere contrato ni orden previa" in t["texto"]
