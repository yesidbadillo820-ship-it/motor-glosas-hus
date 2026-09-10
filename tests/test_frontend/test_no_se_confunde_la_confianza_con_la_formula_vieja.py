"""Dos números distintos no pueden llamarse igual en la misma pantalla.

09-09-2026. El panel del diagnóstico mostraba «Confianza promedio por
modelo: 77%» y ese 77% NO era la Confianza: era el promedio de `score`, la
fórmula vieja de probabilidad de éxito (99 si es extemporánea, 92
ratificación, 90 urgencia, 75 tarifa, 85 el resto). El auditor ve 51% al pie
de sus dictámenes y llevaba semanas diciendo que la confianza no le sube.

Leyendo ese 77% la conclusión natural era «el modelo está bien, no hay que
cambiarlo» — sobre un número que no mide el modelo por ningún lado. Un
rótulo equivocado en un tablero de decisión no es un detalle de redacción:
es la decisión, tomada mal.

QUÉ CUIDA ESTA PRUEBA. Que cada número se llame por su nombre, que la
fórmula vieja salga advertida de lo que no es, y que mientras la Confianza
real no tenga datos guardados la pantalla lo diga en vez de mostrar un cero
que se leería como «el motor saca cero».
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"


@pytest.fixture(autouse=True)
def _hay_node():
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")


def _texto(datos: dict, tmp_path: Path) -> str:
    """Lo que el auditor LEE, sin etiquetas ni estilos.

    Hace falta de verdad: buscar «0%» sobre el HTML crudo encuentra el
    `width:100%` de una tabla y da por bueno lo que no lo es.
    """
    import re

    plano = re.sub(r"<[^>]+>", " ", _pintar(datos, tmp_path))
    return re.sub(r"\s+", " ", plano)


def _pintar(datos: dict, tmp_path: Path) -> str:
    pagina = INDEX.read_text(encoding="utf-8", errors="ignore")
    ini = pagina.index("function _diagBloque(")
    fin = pagina.index("// ─── TEST SENTRY (solo SUPER_ADMIN)")
    guion = tmp_path / "pintar.mjs"
    guion.write_text(
        "function escHtml(v){if(v===null||v===undefined)return '';"
        "return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        + pagina[ini:fin]
        + "\nprocess.stdout.write(_pintarDiagnostico("
        + json.dumps(datos, ensure_ascii=False)
        + "));\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        ["node", str(guion)], capture_output=True, text=True, timeout=30, check=False
    )
    assert r.returncode == 0, f"El panel reventó:\n{r.stderr}"
    return r.stdout


# Lo que devuelve el servidor HOY en el hospital: 397 glosas con la fórmula
# vieja y ni una con Confianza guardada, porque se empezó a guardar hoy.
COMO_ESTA_HOY = {
    "glosas_analizadas": 397,
    "probabilidad_exito_por_modelo": [
        {"modelo": "groq/openai/gpt-oss-120b", "glosas": 382, "promedio": 77.0},
        {"modelo": "texto_fijo", "glosas": 12, "promedio": 60.7},
    ],
    "confianza_por_modelo": {
        "glosas_con_confianza_guardada": 0,
        "de_un_total_de": 397,
        "detalle": [],
        "diagnostico": "Todavía no hay ninguna glosa con la Confianza guardada.",
    },
}

# Cómo se verá en unos días, con datos de los dos modelos.
CON_DATOS = {
    "glosas_analizadas": 420,
    "probabilidad_exito_por_modelo": [
        {"modelo": "groq/openai/gpt-oss-120b", "glosas": 400, "promedio": 77.0}
    ],
    "confianza_por_modelo": {
        "glosas_con_confianza_guardada": 23,
        "de_un_total_de": 420,
        "detalle": [
            {
                "modelo": "groq/openai/gpt-oss-120b",
                "glosas": 15,
                "confianza_promedio": 48.3,
                "peor": 31.0,
                "mejor": 62.5,
            },
            {
                "modelo": "claude-sonnet-4-5",
                "glosas": 8,
                "confianza_promedio": 71.2,
                "peor": 55.0,
                "mejor": 88.0,
            },
        ],
        "diagnostico": "Esta es la comparación buena.",
    },
}


class TestCadaNumeroConSuNombre:
    def test_la_formula_vieja_no_se_llama_confianza(self, tmp_path):
        texto = _texto(COMO_ESTA_HOY, tmp_path)
        i = texto.index("77%")
        titulo = texto.rfind("Probabilidad de éxito", 0, i)
        assert titulo != -1 and i - titulo < 300, (
            "El 77% no está bajo el título de la fórmula antigua. Leído como "
            "«Confianza», lleva a concluir que el modelo está bien — y ese "
            "número no mide el modelo por ningún lado.\n"
            f"Contexto: …{texto[max(0, i - 200) : i + 60]}…"
        )
        assert "fórmula antigua" in texto

    def test_se_advierte_que_no_sirve_para_comparar_modelos(self, tmp_path):
        texto = _texto(COMO_ESTA_HOY, tmp_path)
        assert "NO es la Confianza" in texto
        assert "comparar modelos" in texto, (
            "No se advierte lo único que importa: que con ese número no se puede "
            "decidir el cambio de modelo de IA."
        )

    def test_se_explica_de_donde_sale_el_numero(self, tmp_path):
        """Si el auditor no ve la fórmula, no puede juzgar si le sirve."""
        texto = _texto(COMO_ESTA_HOY, tmp_path)
        for pedazo in ("extemporánea 99", "tarifa 75"):
            assert pedazo in texto, f"No se explica la fórmula: falta «{pedazo}»."


class TestMientrasNoHayaDatos:
    def test_no_se_muestra_un_cero_enganoso(self, tmp_path):
        """Un «0%» de Confianza se leería como «el motor saca cero», que es
        falso: lo que pasa es que todavía no hay nada guardado."""
        texto = _texto(COMO_ESTA_HOY, tmp_path)
        i = texto.index("Confianza real por modelo")
        bloque = texto[i : texto.index("Probabilidad de éxito", i)]
        assert "0%" not in bloque, (
            "Muestra «0%» donde lo que pasa es que todavía no hay nada guardado. "
            "El auditor lo leería como «el motor saca cero de confianza».\n"
            f"Bloque: {bloque[:300]}"
        )
        assert "0 de 397" in bloque

    def test_se_dice_que_hacer_para_que_aparezca(self, tmp_path):
        texto = _texto(COMO_ESTA_HOY, tmp_path)
        assert "Analice unas glosas" in texto, (
            "Dice que no hay datos pero no dice cómo conseguirlos."
        )


class TestCuandoYaHayaDatos:
    def test_sale_la_comparacion_entre_modelos(self, tmp_path):
        html = _pintar(CON_DATOS, tmp_path)
        assert "48.3" in html and "71.2" in html
        assert "claude-sonnet-4-5" in html

    def test_sale_el_peor_y_el_mejor_caso(self, tmp_path):
        """Un promedio esconde la varianza: un modelo con promedio 71 que a
        veces cae a 20 no es igual de confiable que uno parejo."""
        html = _pintar(CON_DATOS, tmp_path)
        assert "31" in html and "88" in html
        assert "Peor" in html and "Mejor" in html

    def test_los_dos_recuadros_conviven_sin_confundirse(self, tmp_path):
        html = _pintar(CON_DATOS, tmp_path)
        assert "Confianza real por modelo" in html
        assert "Probabilidad de éxito (fórmula antigua)" in html
        assert html.index("Confianza real por modelo") < html.index("Probabilidad de éxito"), (
            "La fórmula vieja sale ANTES que la buena: se lee primero el número "
            "que no sirve para decidir."
        )

    def test_sin_undefined_en_pantalla(self, tmp_path):
        for datos in (COMO_ESTA_HOY, CON_DATOS):
            html = _pintar(datos, tmp_path)
            assert "undefined" not in html and "NaN" not in html


class TestElDiagnosticoDiceDondeSeArregla:
    """Un tablero que señala el problema y no dice dónde se arregla se lee una
    vez y no se vuelve a abrir.

    09-09-2026: el hallazgo más grande de la corrida real fue «0 de 397 glosas
    tienen veredicto de la EPS». El panel lo mostraba y ahí quedaba, cuando el
    botón para arreglarlo existe desde hace meses en otra pantalla.
    """

    SIN_VEREDICTOS = {
        "glosas_analizadas": 397,
        "veredicto_final_eps": {
            "con_veredicto": 0,
            "pct": 0,
            "por_estado": [{"estado": "RESPONDIDA", "glosas": 397}],
            "diagnostico": "Menos del 30%: se quedan sin combustible.",
        },
    }

    CON_VEREDICTOS = {
        "glosas_analizadas": 397,
        "veredicto_final_eps": {
            "con_veredicto": 300,
            "pct": 75.6,
            "por_estado": [{"estado": "LEVANTADA", "glosas": 300}],
            "diagnostico": "Suficiente para alimentar precedente y ejemplos.",
        },
    }

    def test_dice_en_que_pantalla_se_marca(self, tmp_path):
        texto = _texto(self.SIN_VEREDICTOS, tmp_path)
        assert "Mis Glosas" in texto, (
            "Señala que faltan los veredictos pero no dice dónde se marcan. El "
            "botón existe hace meses y el auditor no tiene por qué saberlo."
        )

    def test_nombra_los_botones_tal_como_se_ven(self, tmp_path):
        texto = _texto(self.SIN_VEREDICTOS, tmp_path)
        assert "EPS LEVANTÓ" in texto and "EPS RATIFICÓ" in texto, (
            "No nombra los botones con el texto que el auditor ve en pantalla."
        )

    def test_explica_por_que_importa_en_plata_de_confianza(self, tmp_path):
        texto = _texto(self.SIN_VEREDICTOS, tmp_path)
        assert "15 de los 100" in texto, (
            "No dice cuánto pesa: sin el número, «alimenta el precedente» suena "
            "a tecnicismo y se ignora."
        )

    def test_cuando_ya_estan_marcadas_no_se_regana_al_auditor(self, tmp_path):
        """Si el trabajo ya está hecho, el aviso sobra y estorba."""
        texto = _texto(self.CON_VEREDICTOS, tmp_path)
        assert "Qué hacer con esto" not in texto
        assert "EPS LEVANTÓ" not in texto
