"""Guardar una decisión en Glosas ADRES ya no manda al gestor al inicio.

01-09-2026. Yesid: «cada vez que yo digito un dato vuelve y se regresa a la
página de inicio y me toca bajar y mirar y así ya sea que la busque en filtro
o demás siempre me regresa al inicio y eso hace que el trabajo sea mayor».

Pasaba porque `gaBuscar` vaciaba la caja del resultado («Buscando…») también
cuando solo estaba refrescando la MISMA factura tras guardar. La página se
encogía, el navegador subía el scroll, y el gestor quedaba arriba frente a la
lista de facturas.

Se prueba, con las funciones DE VERDAD sacadas del HTML y corridas en Node:

  · que `HUS405315` y `HUS0000405315` cuenten como la misma factura;
  · que con la misma factura la caja vuelva a su altura de pantalla;
  · que con otra factura la vista baje hasta la caja;
  · y, leyendo el código, que el «Buscando…» y el reinicio del filtro solo
    ocurran cuando se cambia de factura.
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


def _correr(guion: str) -> dict:
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")
    texto = _html()
    fuente = "\n".join(
        [
            _fuente_de("gaMismaFactura", texto),
            _fuente_de("gaDejarLaVistaEnSuSitio", texto),
            guion,
        ]
    )
    r = subprocess.run(
        ["node", "-e", fuente], capture_output=True, text=True, timeout=30, encoding="utf-8"
    )
    assert r.returncode == 0, f"el guion falló:\n{r.stderr[:800]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


# Una caja de mentira que "está" a cierta altura de la pantalla, y una ventana
# que apunta cuánto le pidieron desplazarse.
VENTANA = """
var LLAMADAS = {scrollBy: [], scrollIntoView: []};
var window = {scrollBy: function(x, y){ LLAMADAS.scrollBy.push(y); }};
function caja(altura){
  return {
    style: {},
    getBoundingClientRect: function(){ return {top: altura}; },
    scrollIntoView: function(o){ LLAMADAS.scrollIntoView.push(o); }
  };
}
"""


class TestLaMismaFactura:
    def test_con_o_sin_ceros_es_la_misma(self):
        salida = _correr(
            "console.log(JSON.stringify(["
            "gaMismaFactura('HUS405315', 'HUS0000405315'),"
            "gaMismaFactura('hus405315', 'HUS405315'),"
            "gaMismaFactura('HUS405315', 'HUS405316'),"
            "gaMismaFactura('', 'HUS405315'),"
            "gaMismaFactura(null, null)]));"
        )
        assert salida == [True, True, False, False, False]


class TestLaVistaSeQuedaDondeEstaba:
    def test_misma_factura_la_caja_vuelve_a_su_altura(self):
        """Antes de repintar la caja estaba a 640px; después quedó a 900px.
        Se corrige exactamente esa diferencia, ni un píxel más."""
        salida = _correr(
            VENTANA + "var c = caja(900);"
            "gaDejarLaVistaEnSuSitio(c, true, 640);"
            "console.log(JSON.stringify(LLAMADAS));"
        )
        assert salida["scrollBy"] == [260]
        assert salida["scrollIntoView"] == []

    def test_misma_factura_sin_corrimiento_no_toca_nada(self):
        salida = _correr(
            VENTANA + "var c = caja(640);"
            "gaDejarLaVistaEnSuSitio(c, true, 640);"
            "console.log(JSON.stringify(LLAMADAS));"
        )
        assert salida["scrollBy"] == []

    def test_otra_factura_baja_hasta_la_caja(self):
        salida = _correr(
            VENTANA + "var c = caja(2400);"
            "gaDejarLaVistaEnSuSitio(c, false, null);"
            "console.log(JSON.stringify(LLAMADAS));"
        )
        assert salida["scrollBy"] == []
        assert len(salida["scrollIntoView"]) == 1
        assert salida["scrollIntoView"][0]["block"] == "start"

    def test_sin_ventana_no_revienta(self):
        """El banco de pruebas y cualquier render sin DOM no deben fallar."""
        salida = _correr(
            "var window; var ok = true;"
            "try{ gaDejarLaVistaEnSuSitio(null, true, 10); }catch(e){ ok = false; }"
            "console.log(JSON.stringify({ok: ok}));"
        )
        assert salida["ok"] is True


class TestGaBuscarSoloVaciaCuandoCambiaDeFactura:
    def _cuerpo(self) -> str:
        texto = _html()
        m = re.search(r"async function gaBuscar\(\)\{.*?\n\}\n", texto, re.S)
        assert m, "no se encontró gaBuscar en index.html"
        return m.group(0)

    def test_el_buscando_esta_condicionado_a_otra_factura(self):
        cuerpo = self._cuerpo()
        i_misma = cuerpo.index("var misma = ")
        i_buscando = cuerpo.index("Buscando ")
        assert i_misma < i_buscando, "decide si es la misma factura ANTES de vaciar la caja"
        assert "if(!misma){\n    caja.innerHTML" in cuerpo, (
            "el «Buscando…» debe ir solo para otra factura"
        )

    def test_el_filtro_solo_se_reinicia_al_cambiar_de_factura(self):
        cuerpo = self._cuerpo()
        assert (
            "if(!misma) GA_FILTRO = {texto:'', causal:'', clasificacion:'', estado:''};" in cuerpo
        )

    def test_la_vista_se_acomoda_despues_de_pintar(self):
        cuerpo = self._cuerpo()
        assert cuerpo.index("gaPintar(GA_DATOS)") < cuerpo.index(
            "gaDejarLaVistaEnSuSitio(caja, misma, posicion)"
        )

    def test_toma_la_altura_antes_de_repintar(self):
        cuerpo = self._cuerpo()
        assert "caja.getBoundingClientRect().top" in cuerpo
        assert cuerpo.index("var posicion = ") < cuerpo.index("gaPintar(GA_DATOS)")
