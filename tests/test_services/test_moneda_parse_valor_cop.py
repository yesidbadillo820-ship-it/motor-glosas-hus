"""Regresión del bug 100× en valores monetarios (auditoría jun-2026, P0 #1).

Los call sites de analizar.py, glosas.py y schemas.py usaban
float(re.sub(r"[^\\d]", "", x)), que convierte "7.700,00" en 770000
(100× el valor real). El parser correcto vivía en auto_pilot_decision
(_parse_valor); ahora está extraído en app/utils/moneda.parse_valor_cop
y propagado a todos los call sites.
"""

import pytest

from app.utils.moneda import parse_valor_cop


class TestParseValorCopFormatosColombianos:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            # ── El caso del bug 100×: coma decimal ──────────────────────
            ("7.700,00", 7700.0),
            ("7.700,50", 7700.5),
            ("$ 7.700,00", 7700.0),
            ("1.234.567,89", 1234567.89),
            ("0,99", 0.99),
            ("247.663,5", 247663.5),
            # ── Puntos como separadores de miles (sin coma) ─────────────
            ("1.500.000", 1500000.0),
            ("7.700", 7700.0),
            ("12.345", 12345.0),
            # ── Prefijos de moneda y espacios ───────────────────────────
            ("$ 500.000", 500000.0),
            ("$500.000", 500000.0),
            ("COL$ 1.500.000", 1500000.0),
            ("  $ 2.500  ", 2500.0),
            ("% 350.000", 350000.0),
            # ── Apóstrofe como separador de millones (uso regional) ─────
            ("1'500.000", 1500000.0),
            ("$ 1'234.567", 1234567.0),
            # ── Coma con 3+ dígitos detrás NO es decimal ────────────────
            ("1,500,000", 1500000.0),
            ("7,700", 7700.0),
            # ── Enteros planos ──────────────────────────────────────────
            ("500000", 500000.0),
            ("0", 0.0),
        ],
    )
    def test_formatos(self, entrada, esperado):
        assert parse_valor_cop(entrada) == pytest.approx(esperado), (
            f"parse_valor_cop({entrada!r}) = {parse_valor_cop(entrada)} (esperaba {esperado})"
        )

    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            (None, 0.0),
            ("", 0.0),
            ("   ", 0.0),
            ("N/A", 0.0),
            ("SIN VALOR", 0.0),
            (7700, 7700.0),
            (7700.5, 7700.5),
            (0, 0.0),
        ],
    )
    def test_entradas_no_string_o_vacias(self, entrada, esperado):
        assert parse_valor_cop(entrada) == pytest.approx(esperado)

    def test_regresion_bug_100x(self):
        """El bug original: "7.700,00" → 770000 (lectura $770.000)."""
        r = parse_valor_cop("7.700,00")
        assert r == 7700.0
        assert r != 770000.0

    @pytest.mark.parametrize(
        "entrada",
        ["7.700,00", "1.500.000", "$ 500.000", "1'500.000", "1.234.567,89"],
    )
    def test_propiedad_reparse_estable(self, entrada):
        """Re-parsear la representación canónica devuelve el mismo valor
        (propiedad usada por el validator de GlosaInput.valor_aceptado)."""
        v = parse_valor_cop(entrada)
        canonica = str(int(v)) if v == int(v) else f"{v:.2f}".replace(".", ",")
        assert parse_valor_cop(canonica) == pytest.approx(v)


class TestAliasAutoPilotPreservado:
    def test_parse_valor_es_el_parser_compartido(self):
        """glosa_service.py y confidence_scorer.py importan _parse_valor
        desde auto_pilot_decision — el alias debe seguir existiendo y
        apuntar al parser canónico."""
        from app.services.auto_pilot_decision import _parse_valor

        assert _parse_valor is parse_valor_cop


class TestValidatorValorAceptado:
    """GlosaInput.valor_aceptado debe normalizarse sin inflar 100×."""

    def _input(self, valor):
        from app.models.schemas import GlosaInput

        return GlosaInput(
            eps="FAMISANAR",
            etapa="RESPUESTA A GLOSA",
            tabla_excel="TA0201 $1.500.000 Diferencia en consulta",
            valor_aceptado=valor,
        )

    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("7.700,00", "7700"),  # antes: "770000" (bug 100×)
            ("$ 500.000", "500000"),
            ("1.500.000", "1500000"),
            ("7.700,50", "7700,50"),  # decimales reales se conservan
            ("0", "0"),
            ("", "0"),
        ],
    )
    def test_normalizacion(self, entrada, esperado):
        assert self._input(entrada).valor_aceptado == esperado

    def test_canonico_reparsea_igual(self):
        data = self._input("7.700,50")
        assert parse_valor_cop(data.valor_aceptado) == pytest.approx(7700.5)
