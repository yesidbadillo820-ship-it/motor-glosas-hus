"""Cuando el Excel trae dos valores para el mismo codigo, ¿cuál queda?

24-08-2026: el Excel de POSITIVA traia el mismo CUPS varias veces con valores
que no coinciden (el 103204 traia CINCO, de $94.399 a $1.926.567). El parser
los omitia todos: no sabia cual regia y cargar uno al azar produce dictamenes
falsos. Quedaron 256 codigos del Dispensario, 737 de Compensar y 737 de
Positiva sin cargar.

26-08-2026 — DECISION DEL AREA. Yesid: «¿cuál queda? el que mejor se ajuste a
las tarifas pactadas».

Y eso SI se puede probar, porque el contrato tiene formula: se toma el valor
SOAT oficial del codigo (Circular 047/2025), se le aplica el factor del
contrato de esa entidad, y se escoge el candidato que caiga sobre ese numero.

Lo que esta prueba vigila es que NO se convierta en «el mas parecido»: si
ninguno cuadra, o cuadran dos, el codigo se sigue omitiendo. La regla resuelve
lo que puede probar; no adivina el resto.
"""

import pytest

from app.services.tarifas_excel_parser import _el_que_cuadra_con_lo_pactado
from app.services.tarifas_oficiales import buscar_tarifa_soat_2026

CODIGO = "19001"  # Acetaminofén — está en la tabla SOAT 2026


@pytest.fixture(scope="module")
def base() -> float:
    soat = buscar_tarifa_soat_2026(CODIGO)
    assert soat and soat.get("valor_pesos_2026"), "el código de control debe estar en la tabla SOAT"
    return float(soat["valor_pesos_2026"])


def _grupo(*valores):
    return [{"codigo_cups": CODIGO, "valor_pactado": v} for v in valores]


class TestResuelveLoQuePuedeProbar:
    def test_positiva_es_soat_menos_15(self, base):
        elegido, motivo = _el_que_cuadra_con_lo_pactado(
            CODIGO, _grupo(base * 0.85, base * 1.7), "POSITIVA"
        )
        assert elegido is not None
        assert elegido["valor_pactado"] == pytest.approx(base * 0.85)
        assert "−15 %" in motivo

    def test_compensar_es_soat_menos_10(self, base):
        elegido, _ = _el_que_cuadra_con_lo_pactado(
            CODIGO, _grupo(base * 0.90, base * 0.50), "COMPENSAR"
        )
        assert elegido is not None
        assert elegido["valor_pactado"] == pytest.approx(base * 0.90)

    def test_el_motivo_deja_la_cuenta_a_la_vista(self, base):
        """El auditor tiene que poder rehacer la cuenta: valor SOAT y descuento."""
        _, motivo = _el_que_cuadra_con_lo_pactado(CODIGO, _grupo(base * 0.85, base * 2), "POSITIVA")
        assert "SOAT" in motivo and "%" in motivo

    def test_tolera_el_redondeo_del_contrato(self, base):
        """Los Excel del contrato vienen redondeados; 1 % de diferencia sigue
        siendo el mismo valor pactado."""
        elegido, _ = _el_que_cuadra_con_lo_pactado(
            CODIGO, _grupo(base * 0.85 * 1.008, base * 3), "POSITIVA"
        )
        assert elegido is not None


class TestNoAdivinaCuandoNoPuedeProbar:
    def test_si_ninguno_cuadra_no_elige(self, base):
        elegido, _ = _el_que_cuadra_con_lo_pactado(
            CODIGO, _grupo(base * 2.5, base * 3.1), "POSITIVA"
        )
        assert elegido is None, "sin prueba, el código se sigue omitiendo"

    def test_si_dos_cuadran_igual_no_elige(self, base):
        """Dos valores distintos igual de cerca del esperado: el archivo sigue
        sin decir cuál rige."""
        elegido, _ = _el_que_cuadra_con_lo_pactado(
            CODIGO, _grupo(base * 0.85, base * 0.851), "POSITIVA"
        )
        assert elegido is None

    def test_sin_entidad_no_elige(self, base):
        assert _el_que_cuadra_con_lo_pactado(CODIGO, _grupo(base * 0.85, base * 2), "")[0] is None

    def test_un_codigo_que_no_esta_en_la_tabla_soat_no_se_resuelve(self):
        grupo = [
            {"codigo_cups": "999999", "valor_pactado": 1000},
            {"codigo_cups": "999999", "valor_pactado": 2000},
        ]
        assert _el_que_cuadra_con_lo_pactado("999999", grupo, "POSITIVA")[0] is None

    def test_una_entidad_sin_factor_pactado_no_se_resuelve(self, base):
        """Sin contrato con fórmula no hay contra qué comparar."""
        assert (
            _el_que_cuadra_con_lo_pactado(CODIGO, _grupo(base, base * 2), "OTRA / SIN DEFINIR")[0]
            is None
        )
