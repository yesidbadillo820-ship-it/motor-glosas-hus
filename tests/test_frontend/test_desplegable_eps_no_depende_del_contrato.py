"""El desplegable de Analizar no puede depender de tener contrato cargado.

09-09-2026. SURA, SALUD TOTAL, EMSSANAR, SAVIA y MUTUAL SER —entidades
reales, con bot de portal propio— nunca aparecían en «EPS / Entidad
Pagadora» porque el desplegable se llenaba solo con `/contratos/` (las
que tienen `ContratoRecord`). El auditor solo podía elegir
«OTRA / SIN DEFINIR», y todo dictamen de esas EPS salía genérico.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
HTML = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")


def _funcion(nombre: str) -> str:
    i = HTML.index(f"function {nombre}(")
    siguiente = HTML.find("\nfunction ", i + 1)
    return HTML[i : siguiente if siguiente > 0 else i + 4000]


class TestElDesplegableUsaElCatalogoCompleto:
    def test_llama_a_la_ruta_de_entidades_seleccionables(self):
        cuerpo = _funcion("loadContratos")
        assert "/contratos/eps-seleccionables" in cuerpo

    def test_las_agrega_al_select_de_analizar(self):
        cuerpo = _funcion("loadContratos")
        i = cuerpo.index("/contratos/eps-seleccionables")
        trozo = cuerpo[i : i + 500]
        assert "sel.innerHTML" in trozo, (
            "sin esto, las entidades sin contrato se piden pero no se muestran"
        )

    def test_un_fallo_de_esa_llamada_no_tumba_la_pantalla_y_se_avisa(self):
        """No puede ser un catch mudo (regla del MASTER_IMPROVEMENT_PLAN,
        1.3): el auditor tiene que saber que la lista puede estar incompleta."""
        cuerpo = _funcion("loadContratos")
        i = cuerpo.index("/contratos/eps-seleccionables")
        trozo = cuerpo[max(0, i - 200) : i + 600]
        assert "catch" in trozo and "avisarNoCargo(" in trozo

    def test_la_grilla_de_contratos_sigue_mostrando_solo_contratos_reales(self):
        """La grilla de la pantalla Contratos NO debe inflarse con entidades
        sin contrato — esas se ven ahí como si tuvieran uno."""
        cuerpo = _funcion("loadContratos")
        i = cuerpo.index("data.forEach")
        j = cuerpo.index("/contratos/eps-seleccionables")
        assert i < j, "la grilla se llena con /contratos/, antes de la unión"
        trozo_grilla = cuerpo[i:j]
        assert "contrato-card" in trozo_grilla
