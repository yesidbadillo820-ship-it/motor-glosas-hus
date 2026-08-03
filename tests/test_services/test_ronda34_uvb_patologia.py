"""Ronda 34 (03-ago-2026): dos reglas del caso real TA0801 / CUPS 898015H.

Evidencia: glosa de la factura 1344527 pegada por Yesid — la entidad
liquidó a "SOAT UVB según Decreto 1760/2022", alegó "IPS sin acuerdo de
voluntades" y ajustó $1.700 sobre una citología de $45.500. Una IA externa
asumió que era accidente de tránsito (defensa que se derrumba si no lo
fue) y no hizo la cuenta de la UVB. Estas reglas parametrizan la lectura
correcta:

  1. «SE RECONOCE SOAT UVB» + «SIN ACUERDO DE VOLUNTADES» = liquidación a
     SOAT por falta de contrato, NO tránsito → SOAT pleno sin descuentos,
     UVB vigente por fecha de atención, y exigir el desglose del ajuste.
  2. «AYUDA DIAGNÓSTICA NO INTERPRETADA» sobre patología/citologías: la
     interpretación es inherente al servicio — el producto ES el informe.
"""

from __future__ import annotations

from app.services.glosa_ia_prompts import get_system_prompt


def _prompt() -> str:
    return get_system_prompt("TA", "COMPENSAR")


class TestReglaSoatUvbSinContrato:
    def test_prohibe_asumir_accidente_de_transito(self):
        p = _prompt()
        assert "8.quindecies" in p
        assert "NO ES ACCIDENTE DE TRÁNSITO" in p
        assert "PORQUE NO HAY CONTRATO" in p

    def test_exige_soat_pleno_y_uvb_vigente_por_fecha(self):
        p = _prompt()
        assert "SOAT PLENA" in p
        assert "UVB VIGENTE A LA FECHA DE ATENCIÓN" in p
        assert "desglose aritmético" in p

    def test_los_ajustes_pequenos_tienen_explicacion(self):
        """El caso real: $1.700 sobre $45.500 — UVB vieja o descuento sin
        pacto. La regla obliga a decirlo con la cuenta, no como sospecha."""
        p = _prompt()
        assert "UVB del año anterior" in p
        assert "sin pacto" in p


class TestReglaInterpretacionInherente:
    def test_la_interpretacion_es_el_servicio(self):
        p = _prompt()
        assert "8.sexdecies" in p
        assert "AYUDA DIAGNÓSTICA NO INTERPRETADA" in p
        assert "INHERENTE al servicio" in p
        assert "898" in p  # el grupo de anatomopatológicos queda nombrado

    def test_con_la_precaucion_de_toma_vs_lectura(self):
        """La regla no puede ser ciega: hay códigos que sí separan toma y
        lectura — ahí primero se verifica cuál se facturó."""
        p = _prompt()
        assert "separan toma y lectura" in p
