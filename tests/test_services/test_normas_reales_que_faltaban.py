"""Dos normas que el motor citaba bien y el revisor marcaba como inventadas.

Lote de recepcion del 25-08-2026, 117 dictamenes. El revisor de citas marco
5 NORMA_INEXISTENTE de severidad ALTA. Al revisarlas una por una:

  · Ley 1164 de 2007 (3 veces) — EXISTE. Es la ley del Talento Humano en
    Salud (Diario Oficial, 3 de octubre de 2007) y su articulo 26 dice justo
    lo que el dictamen le atribuye: el acto profesional "se caracteriza por
    la autonomia profesional". Lo que faltaba era la norma en el corpus.

  · Resolucion 3100 de 2020 (2 veces) — el NUMERO es correcto, el ANO no:
    la resolucion de habilitacion de servicios es de 2019.

Las dos cosas hacen el mismo dano: la entidad busca la norma, no la
encuentra y trata toda la cita como inventada.
"""

from app.services.glosa_service import _corregir_anio_de_norma
from app.services.normativa_completa import _TODAS_LAS_NORMAS as NORMAS_COMPLETAS


class TestLey1164De2007:
    def test_esta_en_el_corpus(self):
        assert "LEY 1164 DE 2007" in NORMAS_COMPLETAS

    def test_dice_de_que_se_trata(self):
        n = NORMAS_COMPLETAS["LEY 1164 DE 2007"]
        assert "Talento Humano en Salud" in n["titulo"]
        assert n["vigente"] is True

    def test_trae_el_articulo_26_que_es_el_que_se_cita(self):
        arts = NORMAS_COMPLETAS["LEY 1164 DE 2007"]["articulos"]
        assert "26" in arts
        assert "autonomia profesional" in arts["26"]["texto"].lower()

    def test_trae_el_articulo_35_de_principios_eticos(self):
        arts = NORMAS_COMPLETAS["LEY 1164 DE 2007"]["articulos"]
        assert "35" in arts
        assert "autonomia" in arts["35"]["texto"].lower()

    def test_queda_constancia_de_quien_la_verifico_y_cuando(self):
        assert NORMAS_COMPLETAS["LEY 1164 DE 2007"]["verificada"]


class TestResolucion3100:
    def test_esta_en_el_corpus_con_el_ano_bueno(self):
        assert "RESOLUCION 3100 DE 2019" in NORMAS_COMPLETAS
        assert "RESOLUCION 3100 DE 2020" not in NORMAS_COMPLETAS

    def test_es_la_de_habilitacion_de_servicios(self):
        n = NORMAS_COMPLETAS["RESOLUCION 3100 DE 2019"]
        assert "habilitación de servicios" in n["titulo"].lower()

    def test_la_nota_avisa_del_ano(self):
        assert (
            "es de 2019 (25 de noviembre), no de 2020"
            in (NORMAS_COMPLETAS["RESOLUCION 3100 DE 2019"]["notas"])
        )


class TestLaRedQueCorrigeElAno:
    def test_corrige_la_cita_en_mayusculas(self):
        texto = "EL SERVICIO ESTABA HABILITADO CONFORME A LA RESOLUCIÓN 3100 DE 2020."
        salida = _corregir_anio_de_norma(texto)
        assert "RESOLUCIÓN 3100 DE 2019" in salida
        assert "3100 DE 2020" not in salida

    def test_corrige_la_cita_con_barra(self):
        texto = "SEGÚN LA RESOLUCION 3100/2020 EL SERVICIO ESTÁ HABILITADO."
        assert "3100 DE 2019" in _corregir_anio_de_norma(texto).upper()

    def test_no_borra_la_cita_solo_le_arregla_el_ano(self):
        texto = "CONFORME A LA RESOLUCIÓN 3100 DE 2020, EL SERVICIO ESTÁ HABILITADO."
        salida = _corregir_anio_de_norma(texto)
        assert "EL SERVICIO ESTÁ HABILITADO" in salida
        assert "3100" in salida

    def test_no_toca_la_resolucion_bien_citada(self):
        texto = "CONFORME A LA RESOLUCIÓN 3100 DE 2019 EL SERVICIO ESTÁ HABILITADO."
        assert _corregir_anio_de_norma(texto) == texto

    def test_no_toca_otras_resoluciones_de_2020(self):
        texto = "CONFORME A LA RESOLUCIÓN 1155 DE 2020 Y AL DECRETO 064 DE 2020."
        assert _corregir_anio_de_norma(texto) == texto

    def test_texto_vacio_no_rompe(self):
        assert _corregir_anio_de_norma("") == ""
        assert _corregir_anio_de_norma(None) is None
