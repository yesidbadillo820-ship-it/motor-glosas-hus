"""Cada rol ve en el menú lo que le corresponde (21-08-2026).

El menú mostraba sus **34 botones a todo el mundo**. Un auditor veía
«Usuarios», «Mando ejecutivo» e «Inteligencia» —pantallas que no son de su
trabajo— y las abría para encontrarse con un error o con datos ajenos.

**Directiva de Yesid:** el rol AUDITOR ve TODO menos **Inteligencia,
Expediente, Usuarios, Mando ejecutivo e Importar recepción**.

LO QUE ESTO ES Y NO ES, y conviene que quede escrito: esconder un botón
**ordena la pantalla, no protege nada**. Quien sepa la dirección entra igual.
La protección de verdad está en el servidor —crear y borrar usuarios ya exige
rol de administrador— y donde falte, hay que ponerla allá, no acá.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[2] / "static" / "index.html"

# Las cinco que el auditor NO debe ver.
RESTRINGIDAS = ("Inteligencia", "Expediente", "Usuarios", "Mando ejecutivo", "Importar recepción")


def _html() -> str:
    return RUTA.read_text(encoding="utf-8")


def _fuente_de(nombre: str, texto: str) -> str:
    m = re.search(r"^function\s+" + re.escape(nombre) + r"\s*\(", texto, re.M)
    assert m, f"no se encontró la función {nombre}"
    i = texto.index("{", m.end() - 1)
    hondo = 0
    for j in range(i, len(texto)):
        if texto[j] == "{":
            hondo += 1
        elif texto[j] == "}":
            hondo -= 1
            if hondo == 0:
                return texto[m.start() : j + 1]
    raise AssertionError(f"{nombre} quedó sin cerrar")


def _correr(guion: str) -> str:
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")
    r = subprocess.run(
        ["node", "-e", guion], capture_output=True, text=True, timeout=30, encoding="utf-8"
    )
    assert r.returncode == 0, f"el JavaScript falló:\n{r.stderr[:800]}"
    return r.stdout.strip()


class TestLasCincoEstanMarcadas:
    @pytest.mark.parametrize(
        "boton", ["Inteligencia", "Expediente", "Usuarios", "Importar recepción"]
    )
    def test_el_boton_lleva_la_marca(self, boton):
        """Se marca con un atributo en el propio botón: agregar o quitar una
        pantalla después es cambiar una palabra, no buscar código."""
        t = _html()
        i = t.index(f'data-tip="{boton}"')
        # El atributo va en la misma etiqueta <button>.
        inicio = t.rindex("<button", 0, i)
        assert 'data-solo-coordinacion="1"' in t[inicio:i], (
            f"«{boton}» no está marcado: el auditor lo va a seguir viendo"
        )

    def test_el_mando_ejecutivo_ya_estaba_resuelto(self):
        """Tenía su propia lógica desde antes. No se tocó: funcionaba."""
        t = _html()
        assert 'id="sn-mando"' in t
        assert "SUPER_ADMIN" in t and "COORDINADOR" in t


class TestQuienEsDeCoordinacion:
    def _es(self, rol: str) -> str:
        t = _html()
        guion = (
            "var localStorage={getItem:function(){return null}};\n"
            "var window={USER_ROL:"
            + repr(rol)
            + "};\n"
            + _fuente_de("esDeCoordinacion", t)
            + "\nconsole.log(esDeCoordinacion());"
        )
        return _correr(guion)

    @pytest.mark.parametrize("rol", ["SUPER_ADMIN", "COORDINADOR"])
    def test_coordinacion_si(self, rol):
        assert self._es(rol) == "true"

    @pytest.mark.parametrize("rol", ["AUDITOR", "VIEWER", "", "auditor"])
    def test_el_auditor_no(self, rol):
        assert self._es(rol) == "false"


class TestSeAplicaDeVerdadSobreElMenu:
    """Se ejecuta la función real contra un menú de mentira."""

    def _visibles(self, rol: str) -> list[str]:
        t = _html()
        guion = f"""
var _marcados = [
  {{tip:'Inteligencia', style:{{display:''}}, classList:{{contains:function(){{return false}}}}}},
  {{tip:'Usuarios',     style:{{display:''}}, classList:{{contains:function(){{return false}}}}}},
  {{tip:'Soportes',     style:{{display:''}}, classList:{{contains:function(){{return false}}}}}}
];
var window = {{USER_ROL: {rol!r}}};
var localStorage = {{getItem:function(){{return null}}}};
var document = {{
  querySelectorAll: function(sel){{
    if(sel.indexOf('data-solo-coordinacion') >= 0) return _marcados.slice(0,2);
    return [];
  }}
}};
{_fuente_de("esDeCoordinacion", t)}
{_fuente_de("aplicarPermisosDelMenu", t)}
aplicarPermisosDelMenu();
console.log(JSON.stringify(_marcados.map(function(x){{
  return {{tip:x.tip, visible: x.style.display !== 'none'}};
}})));
"""
        import json

        return [x["tip"] for x in json.loads(_correr(guion)) if x["visible"]]

    def test_el_auditor_no_ve_las_restringidas(self):
        v = self._visibles("AUDITOR")
        assert "Inteligencia" not in v
        assert "Usuarios" not in v

    def test_pero_sigue_viendo_lo_suyo(self):
        """Lo importante: el auditor NO pierde nada de su trabajo diario."""
        assert "Soportes" in self._visibles("AUDITOR")

    def test_coordinacion_lo_ve_todo(self):
        v = self._visibles("COORDINADOR")
        assert "Inteligencia" in v and "Usuarios" in v


class TestElBuscadorRespetaLoMismo:
    def test_no_ofrece_lo_que_el_menu_esconde(self):
        """Esconder el botón no sirve de nada si ⌘K sigue ofreciendo la misma
        pantalla."""
        t = _html()
        assert "soloCoordinacion" in t
        i = t.index("CP_FILTERED = CP_ACCIONES.filter")
        assert "esDeCoordinacion()" in t[i : i + 400]

    def test_importar_recepcion_esta_marcada_en_el_buscador(self):
        t = _html()
        i = t.index('titulo:"Importar recepción"')
        assert "soloCoordinacion:true" in t[i : i + 200]


class TestSeAplicaCuandoDebe:
    def test_al_entrar(self):
        t = _html()
        i = t.index("USER_ROL=d.rol")
        assert "aplicarPermisosDelMenu()" in t[i : i + 300]

    def test_y_al_recargar_con_la_sesion_abierta(self):
        """El caso que de verdad importa: sin esto los botones reaparecen en
        cada F5 y el orden del menú dura un solo rato."""
        t = _html()
        i = t.index("window.addEventListener('DOMContentLoaded',function(){")
        assert "aplicarPermisosDelMenu()" in t[i : i + 600]

    def test_si_falla_no_tumba_el_arranque(self):
        """Un menú mal ordenado es un problema; un portal que no abre es otro
        mucho peor."""
        t = _html()
        i = t.index("window.addEventListener('DOMContentLoaded',function(){")
        trozo = t[i : i + 600]
        assert "try{" in trozo and "catch" in trozo
