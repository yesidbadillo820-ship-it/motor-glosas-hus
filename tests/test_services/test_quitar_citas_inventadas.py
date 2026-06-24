"""Tests del nuevo postprocessor quitar_parrafos_con_citas_inventadas.

Bug reportado por Yesid (21 mayo 2026): pese al banco HUS funcionando,
la IA sigue agregando oraciones tipo "DE ACUERDO CON EL ARTÍCULO 10 DE
LA LEY 1438..." con citas que el validador HUS marca como NORMA_INEXISTENTE.

Este postprocessor identifica esas citas frecuentemente inventadas y
elimina las oraciones que las mencionan, dejando intactas las oraciones
con citas verificadas (Art. 87 Decreto 2423, Art. 1602 CC, etc.).
"""

from __future__ import annotations

from app.services.dictamen_postprocesor import quitar_parrafos_con_citas_inventadas


DICTAMEN_REAL_POLICIA = (
    "ESE HUS NO ACEPTA LA GLOSA TA0201 POR CONCEPTO DE DIFERENCIA TARIFARIA. "
    "DE ACUERDO CON EL ARTÍCULO 10 DE LA LEY 1438 DE 2011, EL ARTÍCULO 15 "
    "DE LA LEY 1122 DE 2007 Y EL ARTÍCULO 2 DE LA LEY 1751 DE 2015, SE "
    "ESTABLECEN LOS PARÁMETROS PARA LA FACTURACIÓN. "
    "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO ÍNTEGRO DE LO FACTURADO."
)


class TestEliminacionCitasInventadas:
    def test_quita_oracion_con_art_10_ley_1438(self):
        out = quitar_parrafos_con_citas_inventadas(DICTAMEN_REAL_POLICIA)
        assert "Art. 10" not in out
        assert "ARTÍCULO 10" not in out
        # La cita inventada ya no está
        assert "Ley 1438 de 2011" not in out  # se quitó toda la oración

    def test_preserva_encabezado_y_cierre(self):
        out = quitar_parrafos_con_citas_inventadas(DICTAMEN_REAL_POLICIA)
        assert "ESE HUS NO ACEPTA" in out
        assert "SE SOLICITA EL LEVANTAMIENTO" in out
        assert "PAGO ÍNTEGRO" in out

    def test_no_toca_dictamen_sin_citas_inventadas(self):
        texto_limpio = (
            "ESE HUS NO ACEPTA LA GLOSA. EL ARTÍCULO 87 DEL DECRETO 2423 DE 1996 "
            "ESTABLECE QUE LA TARIFA INSTITUCIONAL PREVALECE. EL ARTÍCULO 1602 "
            "DEL CÓDIGO CIVIL CONFIRMA. SE SOLICITA EL LEVANTAMIENTO."
        )
        out = quitar_parrafos_con_citas_inventadas(texto_limpio)
        assert out == texto_limpio  # idempotente sobre texto limpio

    def test_no_borra_demasiado(self):
        """Si la única oración del texto es una cita inventada, NO borra
        todo (devuelve original) — evita destruir el dictamen."""
        texto_corto = "DE ACUERDO CON EL ARTÍCULO 10 DE LA LEY 1438 DE 2011, X."
        out = quitar_parrafos_con_citas_inventadas(texto_corto)
        # Resultado debería ser el original (porque borrar todo sería <40%)
        assert out == texto_corto

    def test_quita_multiples_citas_inventadas(self):
        texto = (
            "ORACION UNO. EL ARTÍCULO 10 DE LA LEY 1438 NO EXISTE. "
            "ORACION TRES. EL ARTÍCULO 14 DE LA LEY 1438 TAMPOCO. "
            "ORACION CINCO. ORACION SEIS. ORACION SIETE. ORACION OCHO."
        )
        out = quitar_parrafos_con_citas_inventadas(texto)
        assert "Art. 10" not in out
        assert "Art. 14" not in out
        assert "ORACION UNO" in out
        assert "ORACION TRES" in out

    def test_input_vacio_no_explota(self):
        assert quitar_parrafos_con_citas_inventadas("") == ""
        assert quitar_parrafos_con_citas_inventadas(None) is None

    def test_idempotente(self):
        once = quitar_parrafos_con_citas_inventadas(DICTAMEN_REAL_POLICIA)
        twice = quitar_parrafos_con_citas_inventadas(once)
        assert once == twice
