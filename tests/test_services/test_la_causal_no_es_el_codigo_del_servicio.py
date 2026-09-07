"""El código de la glosa nunca es el código del servicio.

27-08-2026, dictamen GL-135 (factura HUS468334). La IA escribió:

    «EL PROCEDIMIENTO FACTURADO CON CUPS SO0102»

**SO0102 es la CAUSAL de la glosa**, no el procedimiento. Presentarla como
código del servicio deja al hospital en evidencia: la entidad ve de una que
confundió su propia objeción con lo que facturó.

Y LO PEOR ERA EL ARREGLO DE ESA MISMA MAÑANA. La red que quita CUPS inventados
había pasado a dejar como «código» cualquier número que estuviera en el
expediente. SO0102 SÍ está en el expediente —es el texto de la glosa—, así que
«CUPS SO0102» salía convertido en «código SO0102»: un disparate que saltaba a
la vista quedaba convertido en algo creíble. **Se lavó el error en vez de
mostrarlo.**

Una causal se borra entera. No es un código que la entidad reconozca como
servicio, y no hay forma honesta de presentarlo.

De paso: el aviso salía repetido («348240, 348240») cuando el mismo código
aparecía dos veces en el texto.
"""

from __future__ import annotations

from app.services.glosa_service import (
    _es_codigo_de_glosa,
    _neutralizar_cups_sin_respaldo,
)


class TestReconocerUnaCausal:
    def test_las_causales_de_las_seis_familias_se_reconocen(self):
        for causal in ("SO0102", "TA0201", "FA0301", "CL0801", "AU0202", "CO0101"):
            assert _es_codigo_de_glosa(causal), f"{causal} es una causal de glosa"

    def test_un_cups_de_verdad_no_es_una_causal(self):
        assert not _es_codigo_de_glosa("890201")

    def test_un_numero_cualquiera_tampoco(self):
        assert not _es_codigo_de_glosa("348240")

    def test_vacio_no_rompe(self):
        assert not _es_codigo_de_glosa("")
        assert not _es_codigo_de_glosa(None)


class TestLaCausalSeBorra:
    def test_el_caso_real_del_gl_135(self):
        d = "EL PROCEDIMIENTO FACTURADO CON CUPS SO0102, APLICANDOSE LA TARIFA"
        r = _neutralizar_cups_sin_respaldo(d, "la glosa SO0102 dice falta de soportes")
        assert "SO0102" not in r, (
            "la causal se borra entera: no hay forma honesta de presentarla como "
            "el código del servicio"
        )
        assert "PROCEDIMIENTO FACTURADO" in r, "se conserva la frase"

    def test_no_la_deja_como_codigo_aunque_este_en_el_expediente(self):
        """El defecto que introdujo el arreglo de la mañana."""
        d = "SERVICIO CON CUPS TA0201"
        r = _neutralizar_cups_sin_respaldo(d, "glosa TA0201")
        assert "código TA0201" not in r, "eso era lavar el error, no corregirlo"
        assert "TA0201" not in r


class TestLoQueSeConserva:
    def test_un_codigo_del_expediente_que_no_es_causal_sigue_como_codigo(self):
        d = "SERVICIO CON CUPS 348240"
        r = _neutralizar_cups_sin_respaldo(d, "DGH tiene 348240")
        assert "código 348240" in r
        assert "REVISE EL CÓDIGO ANTES DE RADICAR" in r

    def test_el_aviso_no_repite_el_mismo_codigo(self):
        d = "SERVICIO CON CUPS 348240 Y CUPS 348240"
        r = _neutralizar_cups_sin_respaldo(d, "DGH tiene 348240")
        assert r.count("348240,") == 0, "salía «348240, 348240» en el GL-135"
        aviso = r.split("REVISE EL CÓDIGO ANTES DE RADICAR", 1)[1]
        assert aviso.count("348240") == 1

    def test_un_cups_valido_no_se_toca(self):
        d = "SERVICIO CON CUPS 890201"
        assert _neutralizar_cups_sin_respaldo(d, "") == d


class TestSinFechaNoSeCitaLaDerogada:
    def test_el_prompt_lo_ordena(self):
        """El GL-135 citó la 3047 con «Fechas no ingresadas»: la instrucción
        era condicional a un dato que el modelo no tenía."""
        from app.services import glosa_ia_prompts

        import inspect

        fuente = inspect.getsource(glosa_ia_prompts)
        assert "SI NO CONOCES LA FECHA DEL SERVICIO, NO LAS CITES" in fuente
