"""El encabezado tiene que decir de qué período habla.

01-09-2026. El encabezado mostraba «148 glosas · $ 426.815.240» y su tooltip
decía «Glosas analizadas hoy». El dato nunca fue de hoy: sale de
`glosa_repository.analytics()`, que filtra por `extract('month', creado_en) ==
mes actual`.

A la medianoche del 1 de septiembre el filtro pasó de agosto a septiembre y el
encabezado amaneció en «0 glosas · $0». El auditor creyó que se habían borrado
las 148 glosas de agosto. No se perdió nada —«42 pendientes» siguió intacto
porque /glosas/alertas no filtra por mes— pero el susto se lo llevó igual.

La métrica está bien. Lo que engañaba era el rótulo.
"""

import io
import re

import pytest

HTML = io.open("static/index.html", encoding="utf-8").read()
REPO = io.open("app/repositories/glosa_repository.py", encoding="utf-8").read()


class TestElRotuloDiceElPeriodo:
    def test_el_numero_va_acompanado_de_este_mes(self):
        assert "' glosas este mes'" in HTML, (
            "el encabezado volvió a decir solo «N glosas», sin decir de cuándo"
        )

    def test_el_tooltip_ya_no_dice_hoy(self):
        i = HTML.index('id="hdr-kpi-glosas"')
        tag = HTML[i : HTML.index(">", i)]
        assert "este mes" in tag
        assert "hoy" not in tag.lower(), "el tooltip volvió a prometer datos del día"

    def test_avisa_que_arranca_de_cero_cada_mes(self):
        """Es lo que evita el susto del día 1."""
        assert "arranca de cero cada día 1" in HTML

    @pytest.mark.parametrize("kpi", ["hdr-kpi-glosas", "hdr-kpi-recuperado"])
    def test_los_dos_kpis_mensuales_lo_advierten(self, kpi: str):
        i = HTML.index(f'id="{kpi}"')
        tag = HTML[i : HTML.index(">", i)]
        assert "este mes" in tag, kpi


class TestElDatoSigueSiendoMensual:
    """Si el backend dejara de filtrar por mes, el rótulo pasaría a mentir."""

    def test_analytics_filtra_por_mes(self):
        assert 'extract("month", GlosaRecord.creado_en) == now.month' in REPO
        assert 'extract("year", GlosaRecord.creado_en) == now.year' in REPO

    def test_el_encabezado_lee_glosas_mes(self):
        assert "a.glosas_mes" in HTML


class TestLoQueNoSeToco:
    def test_pendientes_sigue_sin_filtro_de_mes(self):
        """Por eso el 1 de septiembre marcaba 42 y no 0: es la prueba de que
        los datos estaban ahí."""
        assert "/glosas/alertas" in HTML
        i = HTML.index("/glosas/alertas")
        assert "glosas_mes" not in HTML[i : i + 400]

    def test_no_se_cambio_la_consulta(self):
        assert re.search(r"func\.count\(GlosaRecord\.id\)", REPO)
