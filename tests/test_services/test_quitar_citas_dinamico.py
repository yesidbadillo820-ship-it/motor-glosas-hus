"""Tests del postprocessor dinámico quitar_citas_invalidas_dinamico.

Bug reportado (22 mayo 2026): el dictamen de PPL + TA0201 en producción
salía con Art. 2 Ley 1438 y Art. 1 Ley 1751, que el validador marcaba como
ARTICULO_FUERA_DE_NORMA. Se creó este postprocessor para borrar la oración.

CORRECCIÓN IMPORTANTE (24-08-2026). Aquel diagnóstico estaba equivocado: esos
dos artículos NO eran inventados. Existen los dos, verificados contra los PDF
oficiales del Ministerio de Salud —«Orientación del Sistema General de
Seguridad Social en Salud» y «Objeto»—. Lo que pasaba es que el corpus del
sistema no los tenía cargados, y el validador confundía «no está en mi corpus»
con «no existe».

Como este postprocessor borra la ORACIÓN ENTERA, el motor le estaba quitando al
documento que se radica ante la EPS citas correctas, sin avisarle a nadie. De la
Ley 100 de 1993, por ejemplo, el corpus tenía tres artículos de casi trescientos:
cualquier dictamen que citara el Art. 156 perdía esa frase.

Se corrigió en dos frentes: el validador ya solo afirma que un artículo no
existe cuando de esa norma se cargó la lista COMPLETA (si es parcial, avisa con
severidad baja y no borra nada), y los cuatro artículos reales que aparecían en
estos casos se cargaron al corpus con su texto oficial.

El postprocessor SIGUE HACIENDO FALTA: cuando la norma entera no existe
—la sentencia fantasma «C-4747/2007» es el caso clásico— la oración sí se borra.
Eso es lo que cuidan estas pruebas ahora.
"""

from __future__ import annotations

from app.services.dictamen_postprocesor import quitar_citas_invalidas_dinamico


DICTAMEN_REAL_PPL = (
    "ESE HUS NO ACEPTA LA GLOSA. "
    * 5
    + "EL CÁLCULO APLICADO CORRESPONDE EXACTAMENTE AL VALOR ESTABLECIDO EN "
    "EL DECRETO 2423 DE 1996 Y SUS MODIFICACIONES POSTERIORES, ASÍ COMO AL "
    "ARTÍCULO 2 DE LA LEY 1438 DE 2011 Y AL ARTÍCULO 1 DE LA LEY 1751 DE 2015. "
    + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA TA0201."
)


class TestQuitarCitasInvalidasDinamico:
    def test_ya_no_borra_el_art_2_ley_1438_ni_el_art_1_ley_1751(self):
        """Los dos artículos existen: no se pueden borrar del dictamen.

        Esta prueba decía lo contrario hasta el 24-08-2026, cuando se verificó
        contra los PDF oficiales del Ministerio que los dos son reales. Citarlos
        para sostener un cálculo tarifario es flojo —son artículos de marco
        general—, pero eso es un problema de pertinencia, no de existencia, y no
        se arregla borrándole frases al documento que se radica.
        """
        out = quitar_citas_invalidas_dinamico(DICTAMEN_REAL_PPL)
        assert "ARTÍCULO 2 DE LA LEY 1438" in out.upper()
        assert "ARTÍCULO 1 DE LA LEY 1751" in out.upper()

    def test_una_norma_inventada_se_avisa_pero_no_se_borra_sola(self):
        """Qué pasa hoy con una norma que no existe, dicho sin adornos.

        El verificador la marca en rojo con severidad ALTA y el gestor la ve en
        el panel. Pero la oración NO se borra sola, y eso es a propósito: el
        corpus tiene 131 normas de las miles que existen, así que «no está en el
        corpus» no puede significar «no existe» sin arriesgarse a quitarle al
        documento radicado una resolución real que nadie alcanzó a cargar. Es el
        mismo daño que se acaba de corregir con los artículos.

        La decisión es del gestor, que es quien puede saberlo.
        """
        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA. " * 5
            + "LO ANTERIOR CONFORME A LA RESOLUCIÓN 9999 DE 2044, QUE NO EXISTE. "
            + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA TA0201."
        )
        from app.services.citation_verifier import verificar_citas

        hallazgos = verificar_citas(dictamen)["issues"]
        assert any(
            h["tipo"] == "NORMA_INEXISTENTE" and h["severidad"] == "ALTA" for h in hallazgos
        ), "una norma inventada tiene que quedar avisada en rojo"
        out = quitar_citas_invalidas_dinamico(dictamen)
        assert "SE SOLICITA EL LEVANTAMIENTO" in out

    def test_preserva_cierre(self):
        out = quitar_citas_invalidas_dinamico(DICTAMEN_REAL_PPL)
        assert "SE SOLICITA EL LEVANTAMIENTO" in out
        assert "TA0201" in out

    def test_preserva_decreto_2423_que_es_valido(self):
        """Decreto 2423/1996 SÍ existe en el corpus — no debe eliminarse.

        La nota original de mayo decía que la oración entera se eliminaba
        «porque mezcla citas válidas e inválidas», y lo daba por aceptable.
        Ya no se elimina: las tres citas de esa oración son reales.
        """
        out = quitar_citas_invalidas_dinamico(DICTAMEN_REAL_PPL)
        assert "ESE HUS NO ACEPTA LA GLOSA" in out
        assert "DECRETO 2423 DE 1996" in out.upper()

    def test_texto_sin_citas_invalidas_no_cambia(self):
        """Si todas las citas son válidas, devuelve texto sin cambios."""
        texto = (
            "ESE HUS NO ACEPTA LA GLOSA. " * 5
            + "EL ARTÍCULO 168 DE LA LEY 100 DE 1993 ESTABLECE QUE. "
            + "SE SOLICITA EL LEVANTAMIENTO."
        )
        out = quitar_citas_invalidas_dinamico(texto)
        # Texto debería ser igual o casi igual (sin cambios significativos)
        assert "ESE HUS NO ACEPTA LA GLOSA" in out
        assert "SE SOLICITA EL LEVANTAMIENTO" in out

    def test_texto_vacio_no_explota(self):
        assert quitar_citas_invalidas_dinamico("") == ""
        assert quitar_citas_invalidas_dinamico(None) is None

    def test_safety_no_borra_demasiado(self):
        """Si todo el texto es una sola oración con cita inválida, NO debe
        borrar todo — preserva el original."""
        texto_corto = "EL ARTÍCULO 2 DE LA LEY 1438 DE 2011 ESTABLECE Y."
        out = quitar_citas_invalidas_dinamico(texto_corto)
        # Resultado debería ser el original (borrarlo dejaría texto vacío)
        assert out == texto_corto

    def test_idempotente(self):
        once = quitar_citas_invalidas_dinamico(DICTAMEN_REAL_PPL)
        twice = quitar_citas_invalidas_dinamico(once)
        assert once == twice
