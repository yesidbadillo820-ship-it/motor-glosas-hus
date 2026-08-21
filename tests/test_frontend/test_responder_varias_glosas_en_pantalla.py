"""El filtro y la respuesta masiva, ejecutando el JavaScript de verdad
(21-08-2026).

Pedido de Yesid: «hay glosas que vienen por 7 ítems y a esos 7 se les da la
misma respuesta, y hoy por hoy lo hacen uno a uno».

Estas pruebas NO leen el HTML como texto: sacan las funciones reales del
portal y las corren en node. Es la única forma de saber que funcionan —el
20-08 una prueba que leía texto dejó pasar un paréntesis suelto que dejó al
hospital sin poder entrar.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[2] / "static" / "index.html"


def _html() -> str:
    return RUTA.read_text(encoding="utf-8")


def _fuente_de(nombre: str, texto: str) -> str:
    """Saca una función completa del HTML, contando llaves."""
    m = re.search(r"^function\s+" + re.escape(nombre) + r"\s*\(", texto, re.M)
    assert m, f"no se encontró la función {nombre} en index.html"
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
    assert r.returncode == 0, f"el JavaScript falló:\n{r.stderr[:900]}"
    return r.stdout.strip()


# La factura real de Yesid: la causal 3209 sobre RX de pie y RX de pierna.
_GLOSAS = [
    {
        "id": 1,
        "causal_codigo": "3209",
        "causal_texto": "La ayuda diagnóstica no tiene justificación",
        "clasificacion": "PERTINENCIA",
        "codigo": "21101",
        "descripcion": "Mano, dedos, puño",
        "valor_glosado": 73500,
        "decision": "",
    },
    {
        "id": 2,
        "causal_codigo": "3209",
        "causal_texto": "La ayuda diagnóstica no tiene justificación",
        "clasificacion": "PERTINENCIA",
        "codigo": "21102",
        "descripcion": "Brazo, pierna, rodilla",
        "valor_glosado": 95400,
        "decision": "",
    },
    {
        "id": 3,
        "causal_codigo": "3206",
        "causal_texto": "El material no está justificado",
        "clasificacion": "PERTINENCIA",
        "codigo": "2016DM",
        "descripcion": "Catéter intravenoso",
        "valor_glosado": 5100,
        "decision": "SE ACEPTA",
    },
    {
        "id": 4,
        "causal_codigo": "4506",
        "causal_texto": "El material hace parte de otro servicio",
        "clasificacion": "FACTURACION",
        "codigo": "2020DM",
        "descripcion": "Apósito adhesivo",
        "valor_glosado": 94200,
        "decision": "",
    },
    {
        "id": 5,
        "causal_codigo": "4506",
        "causal_texto": "El material hace parte de otro servicio",
        "clasificacion": "PERTINENCIA",
        "codigo": "2020DM-2",
        "descripcion": "Apósito, otra área",
        "valor_glosado": 12000,
        "decision": "",
    },
]


def _base(*nombres: str) -> str:
    t = _html()
    return "\n".join(_fuente_de(n, t) for n in nombres)


class TestElAgrupador:
    def _grupos(self) -> list:
        guion = (
            _base("gaClasifEfectiva", "gaGrupos")
            + "\nconsole.log(JSON.stringify(gaGrupos({glosas: %s}).map(function(g){"
            "return {causal:g.causal, clasif:g.clasificacion, n:g.filas.length};})));"
            % json.dumps(_GLOSAS, ensure_ascii=False)
        )
        return json.loads(_correr(guion))

    def test_agrupa_la_causal_que_se_repite(self):
        g = self._grupos()
        assert {"causal": "3209", "clasif": "PERTINENCIA", "n": 2} in g

    def test_una_causal_que_viene_una_sola_vez_no_es_grupo(self):
        """Una alerta de «esta causal viene 1 vez» es ruido."""
        assert not [x for x in self._grupos() if x["causal"] == "3206"]

    def test_la_4506_no_mezcla_facturacion_con_pertinencia(self):
        """La 4506 se reparte glosa por glosa entre dos áreas. Si se agruparan
        juntas, un gestor de facturación arrastraría las de la médica
        auditora."""
        cuatro = [x for x in self._grupos() if x["causal"] == "4506"]
        assert not cuatro, "la 4506 quedó agrupada pese a ser de dos áreas distintas"


class TestElAviso:
    def _html_aviso(self, glosas) -> str:
        guion = (
            "function escHtml(s){return String(s==null?'':s).replace(/[&<>\"']/g,function(c){"
            "return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c];});}\n"
            + _base("gaClasifEfectiva", "gaGrupos", "gaAvisoRepetidas")
            + "\nconsole.log(gaAvisoRepetidas({glosas: %s}));"
            % json.dumps(glosas, ensure_ascii=False)
        )
        return _correr(guion)

    def test_dice_cuantas_veces_viene_y_cuantas_faltan(self):
        h = self._html_aviso(_GLOSAS)
        assert "3209" in h
        assert "2 glosas" in h
        assert "2 sin responder" in h
        assert "Responder las 2 juntas" in h

    def test_sin_causales_repetidas_no_pinta_nada(self):
        h = self._html_aviso([_GLOSAS[2]])
        assert h.strip() == "", "no puede salir un aviso vacío cuando no hay nada que agrupar"

    def test_cuenta_bien_lo_ya_respondido(self):
        glosas = [dict(_GLOSAS[0]), dict(_GLOSAS[1])]
        glosas[0]["decision"] = "SE OBJETA"
        h = self._html_aviso(glosas)
        assert "2 glosas" in h
        assert "1 sin responder" in h


class TestLaBarraDeFiltro:
    def _barra(self, glosas) -> str:
        guion = (
            "function escHtml(s){return String(s==null?'':s).replace(/[&<>\"']/g,function(c){"
            "return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c];});}\n"
            "var GA_FILTRO={texto:'',causal:'',clasificacion:'',estado:''};\n"
            + _base("gaClasifEfectiva", "gaBarraFiltro")
            + "\nconsole.log(gaBarraFiltro({glosas: %s}));" % json.dumps(glosas, ensure_ascii=False)
        )
        return _correr(guion)

    def test_ofrece_solo_las_causales_de_esta_factura(self):
        """Nunca una causal que no está: las opciones salen de los datos."""
        h = self._barra(_GLOSAS)
        assert "3209 (2)" in h
        assert "4506 (2)" in h
        assert "9999" not in h

    def test_con_pocas_filas_el_filtro_estorba_y_no_sale(self):
        assert self._barra(_GLOSAS[:3]).strip() == ""

    def test_avisa_que_los_totales_no_cambian(self):
        """Si el filtro moviera los totales de arriba, el gestor no sabría
        cuánto lleva de verdad."""
        assert 'id="ga-filtro-cuenta"' in self._barra(_GLOSAS)


class TestLasFilasTraenConQueFiltrar:
    def test_el_html_marca_causal_clasificacion_y_estado(self):
        t = _html()
        for attr in ("data-ga-fila", "data-causal", "data-clasif", "data-decidida", "data-busca"):
            assert attr in t, f"falta {attr}: el filtro no tendría con qué trabajar"

    def test_el_texto_de_busqueda_junta_lo_que_el_gestor_escribiria(self):
        t = _html()
        i = t.index("var busca = [")
        trozo = t[i : i + 260]
        for campo in (
            "causal_codigo",
            "causal_texto",
            "codigo",
            "descripcion",
            "observacion_tecnico",
        ):
            assert campo in trozo


class TestLaPlataNoSeComparte:
    def test_el_cuadro_dice_que_no_toca_valores(self):
        t = _html()
        assert "No se toca ningún valor ni cantidad" in t

    def test_el_envio_no_manda_valor_ni_cantidad(self):
        """Protección estructural: si el lote pudiera escribir plata, una
        respuesta masiva podría aceptar de más sobre un ítem chico."""
        t = _html()
        i = t.index("respuesta-en-lote")
        trozo = t[i : i + 700]
        assert "valor_aceptado" not in trozo
        assert "cantidad_aceptada" not in trozo


class TestNoSeInventanFunciones:
    def test_todo_lo_que_llama_existe(self):
        """El 20-08 se llamó a una función que no existía y el error solo
        aparecía al apretar el botón."""
        t = _html()
        for nombre in (
            "gaModal",
            "gaCerrarModal",
            "gaGrupos",
            "gaAplicarFiltro",
            "gaAvisoRepetidas",
        ):
            assert re.search(r"^function\s+" + nombre + r"\s*\(", t, re.M), (
                f"se llama a {nombre} pero no está definida"
            )
