"""La pantalla de Glosas ADRES muestra las cantidades, no solo la plata.

19-08-2026. Yesid: «los gestores necesitan saber las cantidades porque si son
6 ítems pero ellos van a aceptar algo pues no sabrían qué aceptar porque no
sale las cantidades de los ítems glosados».

Se prueban dos cosas:

  · que la tabla traiga las cinco columnas del reporte del ADRES (Cantidad
    Reclamado, Valor Reclamado, Cantidad Aprobada, Valor Aprobado y Valor
    Glosado) más la cantidad glosada, que es la que el gestor necesita;
  · que `gaCantGlosada` — la función DE VERDAD, sacada del HTML y corrida con
    Node — dé el número correcto en los casos reales del paquete 31068.
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


def _correr(glosas: list[dict]) -> list[str]:
    """Ejecuta la `gaCantGlosada` real contra cada glosa."""
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")
    texto = _html()
    guion = "%s\n%s\nconsole.log(JSON.stringify(%s.map(gaCantGlosada)));" % (
        _fuente_de("gaCant", texto),
        _fuente_de("gaCantGlosada", texto),
        json.dumps(glosas, ensure_ascii=False),
    )
    r = subprocess.run(
        ["node", "-e", guion], capture_output=True, text=True, timeout=30, encoding="utf-8"
    )
    assert r.returncode == 0, f"la función falló al ejecutarse:\n{r.stderr[:600]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


class TestLaTablaTraeLasCantidades:
    def test_estan_los_encabezados_de_las_tres_cantidades(self):
        texto = _html()
        assert ">Reclamado</th>" in texto
        assert ">Aprobado por el ADRES</th>" in texto
        assert ">Glosado</th>" in texto

    def test_la_fila_pinta_las_cinco_columnas_del_reporte(self):
        texto = _html()
        for campo in (
            "gaCant(g.cant_reclamada)",
            "fmtCOP(g.valor_reclamado)",
            "gaCant(g.cant_aprobada)",
            "fmtCOP(g.valor_aprobado)",
            "fmtCOP(g.valor_glosado)",
            "gaCantGlosada(g)",
        ):
            assert campo in texto, f"la tabla no muestra {campo}"

    def test_el_dinero_sale_con_el_formato_unico(self):
        """Nada de `toLocaleString` suelto: la plata se escribe con `fmtCOP`."""
        texto = _html()
        assert "fmtCOP(g.valor_reclamado)" in texto
        assert "fmtCOP(g.valor_aprobado)" in texto


class TestLaCantidadGlosada:
    def test_reclamados_menos_aprobados(self):
        # HUS353885, dispositivo 2022DM-0008875-R1: reclamó 3, aprobaron 1.
        assert _correr([{"cant_glosada": 2, "valor_glosado": 9200}]) == ["<b>2</b>"]

    def test_glosa_total_del_renglon(self):
        assert _correr([{"cant_glosada": 3, "valor_glosado": 13800}]) == ["<b>3</b>"]

    def test_glosa_de_tarifa_avisa_que_es_solo_valor(self):
        # HUS354131, CUPS 21706: 1 reclamado, 1 aprobado, $100 glosados. Un
        # «0» pelado se lee como dato faltante; hay que decir por qué es cero.
        salida = _correr([{"cant_glosada": 0, "valor_glosado": 100}])[0]
        assert "solo valor" in salida

    def test_calcula_sola_si_el_backend_no_manda_la_cantidad_glosada(self):
        """Un servidor viejo sin el campo nuevo no deja la columna en blanco."""
        assert _correr([{"cant_reclamada": 3, "cant_aprobada": 1, "valor_glosado": 9200}]) == [
            "<b>2</b>"
        ]

    def test_las_cantidades_enteras_no_salen_con_decimales(self):
        # El ADRES manda 1.0, no 1: en pantalla debe decir «1».
        assert _correr([{"cant_glosada": 2.0, "valor_glosado": 9200}]) == ["<b>2</b>"]


class TestLaCantidadQueSeLeDeclaraAlAdres:
    def test_se_acepta_la_cantidad_glosada_no_la_reclamada(self):
        """Antes prellenaba `cant_reclamada`: declaraba 3 donde solo hay 2."""
        texto = _html()
        m = re.search(r"async function gaDecidir\(id, valor\)\{.*?\n\}\n", texto, re.S)
        assert m, "no se encontró gaDecidir en index.html"
        cuerpo = m.group(0)
        assert "cant_glosada" in cuerpo, "gaDecidir sigue sin mirar la cantidad glosada"
        assert "String(g.cant_reclamada || 1)" not in cuerpo, (
            "gaDecidir vuelve a declarar la cantidad RECLAMADA al ADRES"
        )


# ─── La tabla completa, renderizada de verdad ────────────────────────────────

# Agregar columnas a una tabla armada con `+` de textos es fácil de descuadrar:
# basta con olvidar un `colspan` y los números quedan bajo el encabezado
# equivocado — el gestor leería la cantidad aprobada como si fuera la glosada.
# Por eso esta prueba corre la `gaPintar` REAL y cuenta las celdas.

_DATOS = {
    "factura": "HUS353885",
    "radicacion": "14345108",
    "documento_paciente": "CC-1",
    "gestor": "GESTOR",
    "medico": "MEDICA",
    "estado": "EN PROCESO",
    "paquete": {"numero": "31068"},
    "resumen": {
        "glosas": 2,
        "pendientes": 1,
        "valor_glosado": 9300,
        "valor_aceptado": 0,
        "valor_reclamado": 813700,
    },
    "catalogo_centros": ["FARMACIA"],
    "por_clasificacion": [],
    "items": [],
    "glosas": [
        # El caso de cantidad: 3 reclamados, 1 aprobado, 2 glosados.
        {
            "id": 1,
            "causal_codigo": "1901",
            "causal_texto": "estancia no pertinente",
            "codigo": "2022DM-0008875-R1",
            "descripcion": "EQUIPO DE INFUSION",
            "cant_reclamada": 3,
            "valor_reclamado": 13800,
            "cant_aprobada": 1,
            "valor_aprobado": 4600,
            "cant_glosada": 2,
            "valor_glosado": 9200,
            "clasificacion": "FACTURACION",
            "centro_costos": "FARMACIA",
            "decision": "SE ACEPTA",
            "valor_aceptado": 9200,
            "cantidad_aceptada": "2",
            "observacion_tecnico": "",
        },
        # El caso de tarifa: misma cantidad, menos plata.
        {
            "id": 2,
            "causal_codigo": "1902",
            "causal_texto": "mayor valor cobrado",
            "codigo": "21706",
            "descripcion": "PROCEDIMIENTO",
            "cant_reclamada": 1,
            "valor_reclamado": 799900,
            "cant_aprobada": 1,
            "valor_aprobado": 799800,
            "cant_glosada": 0,
            "valor_glosado": 100,
            "clasificacion": "FACTURACION",
            "centro_costos": "",
            "decision": "",
            "valor_aceptado": 0,
            "cantidad_aceptada": "",
            "observacion_tecnico": "",
        },
    ],
}

_GUION_TABLA = """
global.window = {
  USER_ROL: 'SUPER_ADMIN',
  SDS_FMT: { cop: function(v){ return '$' + Math.round(v || 0); } },
};
function fmtCOP(v){ return window.SDS_FMT.cop(v); }
function escHtml(s){ return String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
var CAPTURA = '';
global.document = { getElementById: function(){ return {
  set innerHTML(v){ CAPTURA = v; }, get innerHTML(){ return CAPTURA; } }; } };
%s
gaPintar(%s);
var cabeza = CAPTURA.split('<tbody>')[0];
var cuerpo = CAPTURA.split('<tbody>')[1].split('</tbody>')[0];
console.log(JSON.stringify({
  cabeceras: cabeza.split('<tr ').slice(1).map(function(fila){
    var n = 0;
    (fila.match(/<th[^>]*>/g) || []).forEach(function(th){
      var m = th.match(/colspan="(\\d+)"/); n += m ? parseInt(m[1], 10) : 1;
    });
    return n;
  }),
  filas: cuerpo.split('<tr ').slice(1).map(function(fila){
    return (fila.match(/<td[ >]/g) || []).length;
  }),
  html: CAPTURA,
}));
"""


def _pintar_tabla() -> dict:
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")
    texto = _html()
    funciones = "\n".join(
        _fuente_de(n, texto)
        for n in (
            "gaCant",
            "gaCantGlosada",
            "gaCeldaArea",
            "gaCeldaCentro",
            "gaCeldaAceptado",
            # 21-08-2026: `gaPintar` ahora llama al aviso de causales repetidas
            # y a la barra de filtro. Sin traerlas, este banco de pruebas
            # revienta con «gaAvisoRepetidas is not defined» — que es justo lo
            # que hizo cuando se agregaron, y por eso esta prueba vale: ejecuta
            # la función de verdad en vez de leer el HTML como texto.
            "gaClasifEfectiva",
            "gaGrupos",
            "gaAvisoRepetidas",
            "gaBarraFiltro",
            "gaAplicarFiltro",
            "gaPintar",
        )
    )
    guion = _GUION_TABLA % (funciones, json.dumps(_DATOS, ensure_ascii=False))
    r = subprocess.run(
        ["node", "-e", guion], capture_output=True, text=True, timeout=30, encoding="utf-8"
    )
    assert r.returncode == 0, f"gaPintar falló al ejecutarse:\n{r.stderr[:800]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


class TestLaTablaNoQuedaDescuadrada:
    def test_los_dos_renglones_de_encabezado_suman_lo_mismo(self):
        res = _pintar_tabla()
        assert len(res["cabeceras"]) == 2, res["cabeceras"]
        assert res["cabeceras"][0] == res["cabeceras"][1], (
            f"los colspan del encabezado de grupo no cuadran con las columnas: {res['cabeceras']}"
        )

    def test_cada_fila_tiene_tantas_celdas_como_columnas(self):
        res = _pintar_tabla()
        assert res["filas"], "no se pintó ninguna glosa"
        for celdas in res["filas"]:
            assert celdas == res["cabeceras"][1], (
                f"una fila trae {celdas} celdas y el encabezado {res['cabeceras'][1]}"
            )

    def test_en_pantalla_salen_las_cantidades_reales(self):
        """3 reclamados, 1 aprobado, 2 glosados — los tres números visibles."""
        html = _pintar_tabla()["html"]
        tabla = html.split("Glosas del ADRES")[1].split("</tbody>")[0]
        assert ">3<" in tabla, "no sale la cantidad reclamada"
        assert ">1<" in tabla, "no sale la cantidad aprobada"
        assert "<b>2</b>" in tabla, "no sale la cantidad glosada"

    def test_el_gestor_ve_el_techo_de_lo_que_puede_aceptar(self):
        html = _pintar_tabla()["html"]
        assert "glosado(s)" in html, "la casilla de aceptado no dice de cuántos ítems"
