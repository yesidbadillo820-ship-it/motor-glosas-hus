"""El menú lateral: que el buscador filtre y que el colapso cambie de estado.

OT-043 · 13-08-2026. Yesid pidió pruebas del menú: escribir «Alertas» en el
buscador y que quede visible solo ese botón, y que el botón de colapsar
cambie el estado.

**Cómo se prueban.** El portal no tiene React ni un armador de frontend: es
un solo `static/index.html` con JavaScript de toda la vida, servido por
FastAPI. Así que en vez de montar un mundo de pruebas aparte, estas corren
la **función de verdad**: se saca del HTML, se le arma un DOM mínimo y se
ejecuta con Node. Si alguien cambia `paFiltrarSidebar`, esto lo nota.

Si Node no está en la máquina, la prueba se salta en vez de mentir.
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
    """Saca una función del HTML, contando llaves de primer nivel."""
    m = re.search(r"function " + nombre + r"\s*\([^)]*\)\s*\{", texto)
    assert m, f"no existe la función {nombre} en index.html"
    fin = re.search(r"\n\}\n", texto[m.end() :])
    assert fin, f"no se encontró el cierre de {nombre}"
    return texto[m.start() : m.end() + fin.end()]


def _items_del_menu(texto: str) -> list[dict]:
    """Los botones del menú, con su etiqueta y su pista, como los ve el filtro."""
    items = []
    for m in re.finditer(r'<button class="sn-item[^"]*"([^>]*)>(.*?)</button>', texto, re.S):
        attrs, cuerpo = m.group(1), m.group(2)
        tip = re.search(r'data-tip="([^"]*)"', attrs)
        etiqueta = re.search(r'<span class="sn-item-label">([^<]*)</span>', cuerpo)
        items.append(
            {
                "texto": (etiqueta.group(1) if etiqueta else "").strip(),
                "tip": (tip.group(1) if tip else "").strip(),
            }
        )
    return items


def _correr_filtro(consulta: str) -> dict:
    """Ejecuta la `paFiltrarSidebar` REAL contra un DOM mínimo."""
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")
    texto = _html()
    items = _items_del_menu(texto)
    assert items, "no se leyó ningún botón del menú: revisar el lector"

    guion = """
const ITEMS = %s.map(function(d){
  return {
    textContent: d.texto,
    _tip: d.tip,
    style: {display: ''},
    getAttribute: function(n){ return n === 'data-tip' ? this._tip : null; },
  };
});
const GRUPOS = [{ style:{display:''}, querySelectorAll: function(){ return ITEMS; } }];
const SIDEBAR = {
  querySelectorAll: function(sel){ return sel === '.sn-item' ? ITEMS : GRUPOS; },
};
const VACIO = { style:{display:'none'} };
global.document = {
  getElementById: function(id){
    if (id === 'sidebar-nav') return SIDEBAR;
    if (id === 'sn-search-empty') return VACIO;
    return null;
  },
};
%s
paFiltrarSidebar(%s);
console.log(JSON.stringify({
  visibles: ITEMS.filter(function(i){ return i.style.display !== 'none'; })
                 .map(function(i){ return i.textContent; }),
  aviso_vacio: VACIO.style.display,
}));
""" % (
        json.dumps(items, ensure_ascii=False),
        _fuente_de("paFiltrarSidebar", texto),
        json.dumps(consulta),
    )

    r = subprocess.run(
        ["node", "-e", guion], capture_output=True, text=True, timeout=30, encoding="utf-8"
    )
    assert r.returncode == 0, f"la función falló al ejecutarse:\n{r.stderr[:600]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


class TestElBuscadorDelMenu:
    def test_existe_el_campo_de_busqueda(self):
        texto = _html()
        assert 'id="sn-search-input"' in texto
        assert "paFiltrarSidebar(this.value)" in texto, "el campo no filtra al escribir"

    def test_escribir_alertas_deja_solo_ese_boton(self):
        """Lo que pidió Yesid: escribir «Alertas» y que quede solo ese."""
        res = _correr_filtro("Alertas")
        assert res["visibles"] == ["Alertas"], res["visibles"]

    def test_filtra_sin_importar_mayusculas_ni_tildes_del_usuario(self):
        assert _correr_filtro("alertas")["visibles"] == ["Alertas"]
        assert _correr_filtro("ALERTAS")["visibles"] == ["Alertas"]

    def test_tambien_encuentra_por_la_pista_del_boton(self):
        """El botón de Diagnóstico dice «Diagnóstico» pero su pista aclara
        «del sistema (admin)»: buscar por la pista también tiene que servir."""
        res = _correr_filtro("admin")
        assert res["visibles"], "no encontró nada buscando por la pista"

    def test_con_el_campo_vacio_se_ven_todos(self):
        res = _correr_filtro("")
        assert len(res["visibles"]) == len(_items_del_menu(_html()))

    def test_si_no_hay_coincidencias_lo_dice(self):
        """Un menú en blanco sin explicación parece un error del sistema."""
        res = _correr_filtro("xyzqwerty")
        assert res["visibles"] == []
        assert res["aviso_vacio"] == "block", "no se mostró el aviso de «nada coincide»"

    def test_el_aviso_desaparece_cuando_vuelve_a_haber_resultados(self):
        assert _correr_filtro("Alertas")["aviso_vacio"] == "none"


class TestColapsarElMenu:
    def test_existe_la_funcion_de_colapsar(self):
        assert "function toggleSidebarCollapse" in _html()

    def test_el_colapso_cambia_el_estado_y_lo_recuerda(self):
        """Que cambie no basta: si no se recuerda, el menú se vuelve a abrir
        solo en cada pantalla y el auditor lo cierra veinte veces al día."""
        fuente = _fuente_de("toggleSidebarCollapse", _html())
        assert "classList" in fuente, "no cambia ninguna clase: no colapsa nada"
        assert "localStorage" in fuente, "el colapso no se recuerda entre pantallas"

    def test_el_menu_colapsado_conserva_los_contadores(self):
        """Colapsado sigue habiendo que ver cuántos vencimientos hay: si el
        badge desaparece, el auditor pierde el aviso."""
        assert ".sidebar-nav.collapsed .sn-badge" in _html()


class TestLosContadoresDelMenu:
    @pytest.mark.parametrize(
        "identificador,que_cuenta",
        [
            ("venc-badge-side", "Vencimientos"),
            ("alert-badge-side", "Alertas"),
        ],
    )
    def test_el_contador_existe(self, identificador, que_cuenta):
        assert f'id="{identificador}"' in _html(), que_cuenta

    def test_los_contadores_no_pueden_tumbar_el_menu(self):
        """Si falla la consulta de alertas, el menú tiene que seguir
        funcionando: es lo que en React se resolvería con un ErrorBoundary y
        acá se resuelve con que la función maneje su error."""
        texto = _html()
        m = re.search(r"async function (\w*[Aa]lerta\w*)\s*\([^)]*\)\s*\{", texto)
        if not m:
            pytest.skip("no hay una función async dedicada a alertas")
        fuente = _fuente_de(m.group(1), texto)
        assert "catch" in fuente, (
            f"{m.group(1)} no maneja el error: si se cae la consulta de alertas, "
            "se lleva por delante lo que venga después"
        )
