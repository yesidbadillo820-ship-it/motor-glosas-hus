"""El lector de valores de Salud Total entiende los dos formatos — 18-08-2026.

Antes leía solo el formato gringo (280000.00). Si el portal mandaba el valor
a la colombiana, el TXT que se radica y los totales de la pantalla quedaban
mil veces menos, o el parser se caía. Esos valores no son cosméticos: van en
el archivo que se sube al portal de la EPS.
"""

from __future__ import annotations

import pytest

from app.services.salud_total_service import GlosaSaludTotal


@pytest.fixture
def glosa():
    return GlosaSaludTotal([""] * 24)


class TestLeeLosDosFormatos:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("280000.00", 280000.0),  # gringo con decimales — el de hoy
            ("93340.00", 93340.0),
            ("20700", 20700.0),  # entero pelado
            ("280.000", 280000.0),  # colombiano con punto de miles
            ("1.589.100,00", 1589100.0),  # colombiano completo (antes se caía)
            ("1589100.00", 1589100.0),
            ("", 0.0),
            (None, 0.0),
        ],
    )
    def test_valor(self, glosa, texto, esperado):
        assert glosa._parse_float(texto) == esperado

    def test_el_de_280000_no_se_lee_como_280(self, glosa):
        """El bug exacto: 280.000 valía 280 con el lector viejo."""
        assert glosa._parse_float("280.000") == 280000.0
        assert glosa._parse_float("280.000") != 280.0

    def test_el_formato_colombiano_completo_no_revienta(self, glosa):
        # float("1.589.100,00".replace(",","")) reventaba.
        assert glosa._parse_float("1.589.100,00") == 1589100.0


class TestLosTotalesSalenBien:
    def test_el_valor_glosado_entra_completo(self):
        """Una fila con el valor a la colombiana suma bien en el total."""
        campos = [""] * 24
        campos[13] = "93.340"  # ValorGlosaTotalxServ a la colombiana
        g = GlosaSaludTotal(campos)
        assert g.valor_glosa_total_serv == 93340.0
