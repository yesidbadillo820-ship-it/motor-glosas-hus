"""Una corrección automática no puede dejar el escrito peor de como estaba.

09-09-2026, caso 5 de la prueba del auditor. En un dictamen del lote salió
publicada esta frase:

    «…LEY 1438 DE 2011 ART. EL DECRETO 780…»

Ninguna norma se cita así. Quedó un «ART.» huérfano, sin número, porque una
de las redes que corrigen el texto borró una cita equivocada y se llevó por
delante el número del artículo que venía detrás.

POR QUÉ NO SE PERSIGUE A LA RED CULPABLE. Son decenas y cada una recorta a su
manera; encontrar cuál fue en cada caso es interminable y el siguiente corte
lo dejaría otra red. Lo que sí se puede afirmar SIEMPRE es el resultado: un
«ART.» sin número detrás no es una cita, es un resto. Y en un documento que
se radica ante la entidad, un resto así es la prueba a la vista de que el
escrito salió sin que nadie lo leyera — que es exactamente lo que la entidad
usa para no tomárselo en serio.

QUÉ CUIDA ESTA PRUEBA. Que el resto se limpie, que se avise (el artículo
perdido puede hacerle falta al gestor) y —lo más importante— que la limpieza
no se coma citas buenas ni frases correctas.
"""

from __future__ import annotations

import pytest

from app.services.glosa_service import _quitar_articulo_huerfano


class TestLoQueSiEsUnResto:
    def test_el_caso_real_del_lote(self):
        roto = (
            "ESE HUS NO ACEPTA LA GLOSA. EL TRÁMITE SE RIGE POR LA LEY 1438 DE 2011 "
            "ART. EL DECRETO 780 DE 2016 REGULA LA MATERIA."
        )
        limpio, corrigio = _quitar_articulo_huerfano(roto)
        assert corrigio
        assert "ART. EL DECRETO" not in limpio
        # La norma NO se borra: sigue sirviendo al argumento.
        assert "LEY 1438 DE 2011" in limpio
        assert "DECRETO 780 DE 2016" in limpio

    @pytest.mark.parametrize(
        "roto",
        [
            "RESOLUCIÓN 2284 DE 2023 ARTÍCULO LA LEY 1438 DE 2011.",
            "LEY 100 DE 1993 ARTS. DEL DECRETO 4747 DE 2007.",
            "DECRETO 4747 DE 2007 ART. Y EL CÓDIGO CIVIL.",
            "LEY 1438 DE 2011 ARTICULO EL MANUAL ÚNICO DE GLOSAS.",
        ],
    )
    def test_otras_formas_del_mismo_corte(self, roto):
        limpio, corrigio = _quitar_articulo_huerfano(roto)
        assert corrigio, roto
        assert limpio != roto


class TestLoQueNoSePuedeTocar:
    """El daño de una limpieza demasiado ansiosa es peor que el defecto: se
    lleva citas buenas de un documento que sí se radica."""

    @pytest.mark.parametrize(
        "bueno",
        [
            "CONFORME AL ART. 57 DE LA LEY 1438 DE 2011.",
            "EL ART. 2.5.3.4.3 DEL DECRETO 780 DE 2016.",
            "ARTÍCULOS 57 Y SIGUIENTES DE LA LEY 1438 DE 2011.",
            "ART. 23 DEL DECRETO 4747 DE 2007.",
            "ARTS. 1602 Y 1603 DEL CÓDIGO CIVIL.",
            # Prosa vaga pero correcta: no es un resto.
            "SEGÚN EL ARTÍCULO DEL DECRETO, NO PROCEDE.",
            "EL ARTÍCULO DEL MANUAL ÚNICO DE GLOSAS LO REGULA.",
        ],
    )
    def test_las_citas_buenas_quedan_intactas(self, bueno):
        limpio, corrigio = _quitar_articulo_huerfano(bueno)
        assert not corrigio, f"Se comió una cita buena: {bueno}"
        assert limpio == bueno

    def test_el_texto_vacio_no_revienta(self):
        assert _quitar_articulo_huerfano("") == ("", False)
        assert _quitar_articulo_huerfano(None) == (None, False)


class TestSeAvisaAdemasDeLimpiar:
    def test_el_dictamen_completo_lo_registra(self):
        """No basta con limpiar: el artículo que se perdió puede hacerle falta
        al gestor, y él tiene que enterarse de que se tocó su escrito."""
        import inspect

        from app.services import glosa_service

        fuente = inspect.getsource(glosa_service)
        i = fuente.index("_quitar_articulo_huerfano(dictamen)")
        alrededor = fuente[i : i + 900]
        assert "_correcciones.append" in alrededor, (
            "Se limpia en silencio. El gestor tiene que saber que una corrección "
            "cortó una cita y que puede faltarle el artículo."
        )
        assert "agrégalo" in alrededor or "agréguelo" in alrededor, "El aviso no dice qué hacer."
