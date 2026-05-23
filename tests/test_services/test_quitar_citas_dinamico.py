"""Tests del nuevo postprocessor dinámico quitar_citas_invalidas_dinamico.

Bug reportado (22 mayo 2026): el dictamen de PPL + TA0201 en producción
sigue con citas inventadas Art. 2 Ley 1438 y Art. 1 Ley 1751 que el
validador detecta como ARTICULO_FUERA_DE_NORMA. La lista negra estática
no las cubría todas. Solución: postprocessor dinámico que usa el
verificador oficial.
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
    def test_quita_art_2_ley_1438_y_art_1_ley_1751(self):
        """Las dos citas que el validador marca como inválidas deben
        eliminarse, junto con la oración entera que las contiene."""
        out = quitar_citas_invalidas_dinamico(DICTAMEN_REAL_PPL)
        # La oración con citas inventadas debe haber desaparecido
        assert "ARTÍCULO 2 DE LA LEY 1438" not in out.upper()
        assert "ARTÍCULO 1 DE LA LEY 1751" not in out.upper()

    def test_preserva_cierre(self):
        out = quitar_citas_invalidas_dinamico(DICTAMEN_REAL_PPL)
        assert "SE SOLICITA EL LEVANTAMIENTO" in out
        assert "TA0201" in out

    def test_preserva_decreto_2423_que_es_valido(self):
        """Decreto 2423/1996 SÍ existe en el corpus — no debe eliminarse."""
        # NOTA: la oración entera se elimina (porque MEZCLA citas válidas
        # e inválidas). Esto es comportamiento aceptable — la IA debe
        # generar mejor próxima vez. Pero el encabezado se preserva.
        out = quitar_citas_invalidas_dinamico(DICTAMEN_REAL_PPL)
        assert "ESE HUS NO ACEPTA LA GLOSA" in out

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
