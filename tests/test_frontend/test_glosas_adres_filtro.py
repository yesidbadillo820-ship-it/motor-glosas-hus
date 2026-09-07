"""El filtro de Glosas ADRES no puede esconder una glosa sin que se vea.

31-08-2026. Jhon, mirando una factura del paquete 31078: «dice q falta 1, pero
no veo dónde la puedo responder». Arriba decía **4 glosas · 1 sin decidir** y en
la tabla solo salían **3**.

La glosa que faltaba sí venía del servidor —por eso la contaban los tiles y
salía su pastilla de clasificación—; lo único que en la pantalla puede esconder
una fila es el filtro. Y el filtro es una variable global: quedaba puesto de la
factura anterior. Como con menos de 5 glosas la barra del filtro no se dibuja,
no había ni dónde verlo ni dónde quitarlo: la glosa desaparecía en silencio.

Se prueban las tres defensas, con las funciones DE VERDAD sacadas del HTML:

  · al abrir una factura, el filtro arranca limpio;
  · si la barra no se dibuja, el filtro se limpia;
  · y aun así, si algo escondiera filas sin barra, se vuelven a mostrar todas.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"


def _html() -> str:
    if not INDEX.exists():  # pragma: no cover
        pytest.skip("static/index.html no está en este entorno")
    return INDEX.read_text(encoding="utf-8", errors="ignore")


def _fuente_de(nombre: str, texto: str) -> str:
    m = re.search(r"function " + nombre + r"\s*\([^)]*\)\s*\{", texto)
    assert m, f"no existe la función {nombre} en index.html"
    fin = re.search(r"\n\}\n", texto[m.end() :])
    assert fin, f"no se encontró el cierre de {nombre}"
    return texto[m.start() : m.end() + fin.end()]


# Un `document` de mentira: solo lo que estas funciones tocan.
DOM = """
function hacerFilas(defs){
  return defs.map(function(d){
    return {
      style: {display: ''},
      _at: d,
      getAttribute: function(k){ return this._at[k.replace('data-','')] || ''; }
    };
  });
}
var FILAS = [];
var HAY_BARRA = false;
var CUENTA = {innerHTML: ''};
var document = {
  querySelectorAll: function(sel){ return FILAS; },
  getElementById: function(id){ return (id === 'ga-filtro-cuenta' && HAY_BARRA) ? CUENTA : null; }
};
"""

# Las 4 glosas de la factura del reporte: 3 de PERTINENCIA (causal 3209) y la
# que no aparecía, de GLOSADA TOTAL POR FURIPS 1.
CUATRO = [
    {"causal": "3209", "clasif": "PERTINENCIA", "decidida": "1", "busca": "hemoclasificacion"},
    {"causal": "3209", "clasif": "PERTINENCIA", "decidida": "1", "busca": "rx antebrazo"},
    {"causal": "3209", "clasif": "PERTINENCIA", "decidida": "1", "busca": "hemoclasificacion"},
    {
        "causal": "1002",
        "clasif": "GLOSADA TOTAL POR FURIPS 1",
        "decidida": "0",
        "busca": "glosada total",
    },
]


def _correr(guion: str) -> dict:
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")
    texto = _html()
    fuente = "\n".join(
        [
            "function escHtml(t){ return String(t == null ? '' : t); }",
            DOM,
            "var GA_FILTRO = {texto:'', causal:'', clasificacion:'', estado:''};",
            _fuente_de("gaSinTildes", texto),
            _fuente_de("gaClasifEfectiva", texto),
            _fuente_de("gaBarraFiltro", texto),
            _fuente_de("gaAplicarFiltro", texto),
            guion,
        ]
    )
    r = subprocess.run(
        ["node", "-e", fuente], capture_output=True, text=True, timeout=30, encoding="utf-8"
    )
    assert r.returncode == 0, f"el guion falló:\n{r.stderr[:800]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


class TestElFiltroHeredadoNoEscondeGlosas:
    def test_con_menos_de_cinco_glosas_el_filtro_se_limpia(self):
        """Sin barra no hay dónde quitarlo, así que no puede quedar puesto."""
        salida = _correr(
            "GA_FILTRO = {texto:'', causal:'3209', clasificacion:'', estado:''};"
            "var barra = gaBarraFiltro({glosas: [1,2,3,4]});"
            "console.log(JSON.stringify({barra: barra, filtro: GA_FILTRO}));"
        )
        assert salida["barra"] == "", "con 4 glosas no se debe dibujar la barra"
        assert salida["filtro"] == {"texto": "", "causal": "", "clasificacion": "", "estado": ""}

    def test_las_cuatro_glosas_quedan_visibles(self):
        """El caso de Jhon: 4 glosas, filtro heredado, y salían 3."""
        salida = _correr(
            "FILAS = hacerFilas(%s);"
            % json.dumps(CUATRO, ensure_ascii=False)
            + "GA_FILTRO = {texto:'', causal:'3209', clasificacion:'', estado:''};"
            "gaBarraFiltro({glosas: FILAS});"
            "gaAplicarFiltro();"
            "console.log(JSON.stringify({"
            "  visibles: FILAS.filter(function(f){return f.style.display !== 'none';}).length}));"
        )
        assert salida["visibles"] == 4, "la glosa de GLOSADA TOTAL POR FURIPS sigue escondida"

    def test_red_de_seguridad_sin_barra_no_se_esconde_nada(self):
        """Aunque el filtro llegara puesto, sin barra se muestran todas."""
        salida = _correr(
            "FILAS = hacerFilas(%s);"
            % json.dumps(CUATRO, ensure_ascii=False)
            + "HAY_BARRA = false;"
            "GA_FILTRO = {texto:'', causal:'', clasificacion:'PERTINENCIA', estado:''};"
            "gaAplicarFiltro();"
            "console.log(JSON.stringify({"
            "  visibles: FILAS.filter(function(f){return f.style.display !== 'none';}).length}));"
        )
        assert salida["visibles"] == 4


class TestElFiltroSigueSirviendo:
    def test_con_barra_el_filtro_esconde_lo_que_debe(self):
        """No se rompió el filtro: con barra a la vista sigue filtrando."""
        salida = _correr(
            "FILAS = hacerFilas(%s);" % json.dumps(CUATRO, ensure_ascii=False) + "HAY_BARRA = true;"
            "GA_FILTRO = {texto:'', causal:'3209', clasificacion:'', estado:''};"
            "gaAplicarFiltro();"
            "console.log(JSON.stringify({"
            "  visibles: FILAS.filter(function(f){return f.style.display !== 'none';}).length,"
            "  aviso: CUENTA.innerHTML}));"
        )
        assert salida["visibles"] == 3
        assert "Mostrando 3 de 4" in salida["aviso"], "no avisa cuántas está escondiendo"

    def test_la_barra_aparece_desde_cinco_glosas(self):
        salida = _correr(
            "var barra = gaBarraFiltro({glosas: [{causal_codigo:'3209', clasificacion:'PERTINENCIA'},"
            "{causal_codigo:'3209', clasificacion:'PERTINENCIA'},"
            "{causal_codigo:'3209', clasificacion:'PERTINENCIA'},"
            "{causal_codigo:'1002', clasificacion:'GLOSADA TOTAL POR FURIPS 1'},"
            "{causal_codigo:'4506', clasificacion:'FACTURACION'}]});"
            "console.log(JSON.stringify({tiene: barra.indexOf('ga-filtro-cuenta') >= 0}));"
        )
        assert salida["tiene"], "con 5 glosas la barra del filtro debe dibujarse"


class TestCadaFacturaSeAbreLimpia:
    def test_al_buscar_una_factura_se_reinicia_el_filtro(self):
        texto = _html()
        m = re.search(r"async function gaBuscar\(\)\{.*?\n\}\n", texto, re.S)
        assert m, "no se encontró gaBuscar en index.html"
        cuerpo = m.group(0)
        assert "GA_FILTRO = {texto:'', causal:'', clasificacion:'', estado:''};" in cuerpo, (
            "gaBuscar no limpia el filtro: se hereda de la factura anterior"
        )
        assert cuerpo.index("GA_FILTRO = {") < cuerpo.index("gaPintar(GA_DATOS)"), (
            "el filtro se debe limpiar ANTES de pintar"
        )
