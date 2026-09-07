"""La resolución que el motor seguía escribiendo aunque ya no rige.

28-08-2026. En el export real de la base del hospital —135 glosas— **nueve
citan la Resolución 3047 de 2008**, derogada desde el 1 de abril de 2026 por
el artículo 20 de la Resolución 2335 de 2023 (en su texto modificado por el
artículo 2 de la Resolución 1886 de 2024).

Se le cambió el prompt a la IA para que no citara normas derogadas sin saber
la fecha del servicio. La citó igual. La instrucción no basta: para eso están
las redes finales, que revisan el texto ya escrito.

Y la red YA EXISTÍA desde el 25 de agosto —la que le pone a la norma derogada
su fecha y su sucesora—, con una sola norma cargada: la 2275 de 2023. La
máquina estaba hecha; nadie le había puesto la 3047. Otra vez la lección de
esta semana: escribir la regla no era el trabajo, el trabajo era comprobar que
llegara.

Tres cosas se arreglaron aquí:

1. **La 3047 —y sus dos hermanas de la misma derogatoria, la 416 de 2009 y la
   4331 de 2012— se cargaron en la red.**
2. **La forma abreviada no se reconocía.** El patrón exigía «RESOLUCIÓN 2275
   DE 2023» completo, así que «Res. 3047/2008» —que es como la escribe el
   propio motor en varios textos fijos— pasaba de largo.
3. **El corpus daba por vigente la Res. 4331 de 2012**, que el mismo artículo
   20 deroga. Con eso, el revisor de citas aprobaba un dictamen fundado en una
   norma muerta: exactamente el defecto que se corrigió el 27-08 en la 3047 y
   que había quedado en su vecina.

NO se reemplaza la norma por la nueva: para un servicio prestado antes del 1
de abril de 2026 la 3047 ERA la aplicable, y cambiarla sería meterle al
dictamen una norma que no regía ese día. Se completa con la regla de fecha.
"""

from __future__ import annotations

from app.services.citation_verifier import verificar_citas
from app.services.glosa_service import _completar_norma_derogada
from app.services.normativa_completa import _TODAS_LAS_NORMAS


class TestLaRedYaConoceLa3047:
    def test_le_pone_la_fecha_de_la_derogatoria(self):
        texto = "CONFORME AL ANEXO TÉCNICO 5 DE LA RESOLUCIÓN 3047 DE 2008, LOS SOPORTES BASTAN."
        salida = _completar_norma_derogada(texto)
        assert "1 DE ABRIL DE 2026" in salida
        assert "RESOLUCIÓN 2335 DE 2023" in salida, "hay que decir QUIÉN la derogó"
        assert "RESOLUCIÓN 2284 DE 2023" in salida, "y cuál rige hoy"

    def test_no_borra_la_cita(self):
        """Para un servicio anterior al 01-04-2026 esa ES la norma aplicable."""
        texto = "CONFORME A LA RESOLUCIÓN 3047 DE 2008 LOS SOPORTES BASTAN."
        assert "RESOLUCIÓN 3047 DE 2008" in _completar_norma_derogada(texto)

    def test_reconoce_la_forma_abreviada(self):
        """«Res. 3047/2008» es como la escribe el propio motor."""
        texto = "CONFORME A LA RES. 3047/2008 LOS SOPORTES BASTAN."
        assert "1 de abril de 2026" in _completar_norma_derogada(texto).lower()

    def test_reconoce_la_abreviatura_tambien_en_la_2275(self):
        """El patrón viejo solo veía la palabra completa."""
        texto = "LA FACTURA CUMPLE LA RES. 2275/2023."
        assert "948 DE 2026" in _completar_norma_derogada(texto).upper()

    def test_tambien_la_416_y_la_4331(self):
        for cita in ("RESOLUCIÓN 416 DE 2009", "RESOLUCIÓN 4331 DE 2012"):
            salida = _completar_norma_derogada(f"SEGÚN LA {cita} EL TRÁMITE ES VÁLIDO.")
            assert "1 DE ABRIL DE 2026" in salida, cita
            assert "RESOLUCIÓN 2335 DE 2023" in salida, cita


class TestNoRepiteLoQueElTextoYaDice:
    def test_calla_si_el_dictamen_ya_explico_la_derogatoria(self):
        texto = (
            "LA RESOLUCIÓN 3047 DE 2008 FUE DEROGADA POR LA RESOLUCIÓN 2335 DE 2023 "
            "A PARTIR DEL 1 DE ABRIL DE 2026."
        )
        assert _completar_norma_derogada(texto) == texto

    def test_que_se_cite_la_2284_no_es_senal_de_que_ya_se_explico(self):
        """El fallo del primer intento de este mismo arreglo.

        Se usó «que el dictamen ya nombre la Res. 2284 de 2023» como señal de
        que la aclaración sobraba. Pero la 2284 es el Manual Único: se cita en
        casi todos los dictámenes, así que la aclaración no habría salido casi
        nunca y el cambio quedaba en nada.
        """
        texto = "LA RESOLUCIÓN 3047 DE 2008 Y LA RESOLUCIÓN 2284 DE 2023 REGULAN LOS SOPORTES."
        assert "1 DE ABRIL DE 2026" in _completar_norma_derogada(texto)

    def test_la_fecha_del_servicio_no_calla_el_aviso(self):
        """El otro fallo del borrador, y el caro de los dos.

        La señal aceptaba «1 de abril de 2026» suelto como prueba de que el
        dictamen ya había explicado la derogatoria. Pero esa fecha puede estar
        ahí por otra razón —la fecha del servicio— y entonces la resolución
        muerta se iba al escrito pelada. Ahora se busca el número de la norma
        que derogó, no la fecha.
        """
        texto = (
            "SERVICIO PRESTADO EL 1 DE ABRIL DE 2026. CONFORME A LA "
            "RESOLUCIÓN 3047 DE 2008 LOS SOPORTES BASTAN."
        )
        assert "RESOLUCIÓN 2335 DE 2023" in _completar_norma_derogada(texto)

    def test_una_sola_vez_aunque_se_cite_dos_veces(self):
        texto = "LA RESOLUCIÓN 3047 DE 2008 Y, DE NUEVO, LA RESOLUCIÓN 3047 DE 2008."
        assert _completar_norma_derogada(texto).count("1 DE ABRIL DE 2026") == 1


class TestElSelloQuedaLimpio:
    def test_despues_de_la_red_el_revisor_ya_no_avisa(self):
        """Es la prueba de que la red y el sello hablan del mismo documento."""
        texto = "CONFORME AL ANEXO TÉCNICO 5 DE LA RESOLUCIÓN 3047 DE 2008, LOS SOPORTES BASTAN."
        antes = [i["tipo"] for i in (verificar_citas(texto).get("issues") or [])]
        assert "NORMA_DEROGADA" in antes, "si esto falla, el revisor dejó de ver el problema"
        despues = [
            i["tipo"]
            for i in (verificar_citas(_completar_norma_derogada(texto)).get("issues") or [])
        ]
        assert "NORMA_DEROGADA" not in despues


class TestElCorpusNoDaPorVivaUnaNormaMuerta:
    def test_la_4331_de_2012_esta_marcada_derogada(self):
        """La deroga el mismo art. 20 que a la 3047, y el corpus la daba viva."""
        ficha = _TODAS_LAS_NORMAS["RESOLUCION 4331 DE 2012"]
        assert ficha["vigente"] is False
        assert "2335" in ficha["derogada_por"]

    def test_la_416_de_2009_esta_cargada(self):
        """El prompt la nombra, así que la IA puede escribirla."""
        ficha = _TODAS_LAS_NORMAS["RESOLUCION 416 DE 2009"]
        assert ficha["vigente"] is False
        assert "1 DE ABRIL DE 2026" in ficha["derogada_por"].upper()

    def test_el_revisor_ya_las_marca(self):
        for cita in ("Resolución 4331 de 2012", "Resolución 416 de 2009"):
            tipos = [i["tipo"] for i in (verificar_citas(f"SEGÚN LA {cita}.").get("issues") or [])]
            assert "NORMA_DEROGADA" in tipos, cita
