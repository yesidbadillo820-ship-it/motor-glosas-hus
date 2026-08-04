"""Ronda 30 — saneo de celdas Excel (#31 inyección de fórmulas, #33 char control)."""

from __future__ import annotations

from app.utils.excel_seguro import sanear_celda_excel


class TestSanearCeldaExcel:
    def test_neutraliza_formula_igual(self):
        assert sanear_celda_excel('=HYPERLINK("http://x")').startswith("'=")

    def test_neutraliza_prefijos_peligrosos(self):
        for pref in ("=", "+", "-", "@"):
            assert sanear_celda_excel(pref + "cmd").startswith("'" + pref)

    def test_texto_normal_intacto(self):
        assert sanear_celda_excel("NO ACEPTA LA GLOSA") == "NO ACEPTA LA GLOSA"

    def test_numeros_intactos(self):
        assert sanear_celda_excel(1500000) == 1500000
        assert sanear_celda_excel(1500.5) == 1500.5
        assert sanear_celda_excel(None) is None

    def test_elimina_caracteres_de_control(self):
        # \x00-\x08, \x0b, \x0c, \x0e-\x1f rompen openpyxl.
        out = sanear_celda_excel("OBSERV\x00ACI\x07ÓN")
        assert "\x00" not in out and "\x07" not in out
        assert "OBSERVACIÓN" in out

    def test_conserva_saltos_y_tabs_legitimos(self):
        out = sanear_celda_excel("linea1\nlinea2\ttab")
        assert "\n" in out and "\t" in out
