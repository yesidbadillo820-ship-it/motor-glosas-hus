"""El panel de evidencia se EJECUTA, no solo se lee.

09-09-2026. Yesid pidió que al analizar una glosa de tarifas apareciera «el
Excel de la tarifa pactada y el valor» para poder analizarlo. Esta prueba
corre el pintor de verdad con Node, contra las formas que devuelve el motor,
y comprueba lo que el auditor termina leyendo en la pantalla.

Va aparte de las pruebas de texto a propósito: buscar cadenas en el HTML
diría que todo está bien aunque en pantalla saliera «undefined» donde va la
tarifa — que es justo el defecto que él sí nota y una prueba de texto no ve.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"

FILA = {
    "codigo_cups": "890201",
    "codigo_ips": "CS-0201",
    "descripcion": "CONSULTA DE PRIMERA VEZ POR MEDICINA ESPECIALIZADA",
    "valor_pactado": 157250.0,
    "tipo_tarifa": "SOAT_PORCENTAJE",
    "factor_ajuste": -15.0,
    "modalidad": "EVENTO",
    "contrato_numero": "CW-2026-FAMISANAR-0142",
    "vigencia_desde": "2026-01-01",
    "vigencia_hasta": "2026-12-31",
    "fuente_archivo": "TARIFAS_FAMISANAR_2026_v3.xlsx",
}

COMPLETO = {
    "fila_del_catalogo": FILA,
    "las_cifras_del_caso": {
        "facturado": 185000.0,
        "pactado": 157250.0,
        "objetado": 27750.0,
        "reconocido": 157250.0,
        "diferencia": 27750.0,
        "no_se_pudo_leer": [],
    },
    "recomendacion": {"accion": "ACEPTAR_PARCIAL"},
    "homologacion": None,
}

SIN_FACTURADO = {
    "fila_del_catalogo": FILA,
    "las_cifras_del_caso": {
        "facturado": None,
        "pactado": 157250.0,
        "objetado": 27750.0,
        "reconocido": None,
        "diferencia": None,
        "no_se_pudo_leer": ["el valor facturado"],
    },
    "recomendacion": None,
    "homologacion": None,
}

COINCIDE = {
    "fila_del_catalogo": FILA,
    "las_cifras_del_caso": {
        "facturado": 157250.0,
        "pactado": 157250.0,
        "objetado": 27750.0,
        "reconocido": None,
        "diferencia": 0.0,
        "no_se_pudo_leer": [],
    },
    "recomendacion": None,
    "homologacion": None,
}


@pytest.fixture(autouse=True)
def _hay_node():
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")


def _pintar(ev, tmp_path: Path) -> str:
    pagina = INDEX.read_text(encoding="utf-8", errors="ignore")
    ini = pagina.index("function renderEvidenciaTarifa(")
    fin = pagina.index("function renderMedallasDictamen(")
    guion = tmp_path / "ev.mjs"
    guion.write_text(
        "function escHtml(v){if(v===null||v===undefined)return '';"
        "return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        "var _f=new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',"
        "minimumFractionDigits:0});\n"
        "function fmtCOP(v){return v?_f.format(v):'$0'}\n"
        "function fmtFechaCorta(v){return v?new Date(v).toLocaleDateString('es-CO'):'—'}\n"
        + pagina[ini:fin]
        + "\nprocess.stdout.write(renderEvidenciaTarifa("
        + json.dumps(ev, ensure_ascii=False)
        + ") || '');\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        ["node", str(guion)], capture_output=True, text=True, timeout=30, check=False
    )
    assert r.returncode == 0, f"El panel reventó:\n{r.stderr}"
    return r.stdout


def _texto(ev, tmp_path: Path) -> str:
    import re

    plano = re.sub(r"<[^>]+>", " ", _pintar(ev, tmp_path))
    return re.sub(r"\s+", " ", plano)


class TestLoQueElAuditorVe:
    def test_ve_la_tarifa_pactada_y_lo_facturado(self, tmp_path):
        txt = _texto(COMPLETO, tmp_path)
        assert "157.250" in txt, "No sale la tarifa pactada, que es lo que se pidió."
        assert "185.000" in txt, "No sale lo que facturó el hospital."

    def test_ve_como_se_pacto_no_solo_cuanto(self, tmp_path):
        """«SOAT -15%» se puede discutir con el contrato en la mano; un número
        pelado, no."""
        assert "SOAT -15%" in _texto(COMPLETO, tmp_path)

    def test_ve_de_que_archivo_salio(self, tmp_path):
        """Para poder ir a comprobarlo por su cuenta."""
        assert "TARIFAS_FAMISANAR_2026_v3.xlsx" in _texto(COMPLETO, tmp_path)

    def test_ve_el_contrato_y_el_servicio(self, tmp_path):
        txt = _texto(COMPLETO, tmp_path)
        assert "CW-2026-FAMISANAR-0142" in txt
        assert "CONSULTA DE PRIMERA VEZ" in txt

    def test_la_diferencia_se_explica_en_castellano(self, tmp_path):
        txt = _texto(COMPLETO, tmp_path)
        assert "por encima de lo pactado" in txt
        assert "27.750" in txt

    def test_cuando_coincide_se_dice_que_la_objecion_no_se_sostiene(self, tmp_path):
        txt = _texto(COINCIDE, tmp_path)
        assert "coincide exactamente" in txt
        assert "no tiene sustento tarifario" in txt


class TestLoQueFaltaTambienSeVe:
    """Un valor que no se pudo leer no puede salir como «$0»: el auditor lo
    leería como una cifra real del caso."""

    def test_no_sale_cero_donde_falta_el_dato(self, tmp_path):
        txt = _texto(SIN_FACTURADO, tmp_path)
        assert "no se pudo leer" in txt
        i = txt.index("Facturado por el HUS")
        assert "$ 0" not in txt[i : i + 60], f"Pinta $0 donde falta el dato: {txt[i : i + 80]}"

    def test_no_se_inventa_una_diferencia(self, tmp_path):
        txt = _texto(SIN_FACTURADO, tmp_path)
        assert "No se puede calcular la diferencia" in txt
        assert "el valor facturado" in txt

    def test_dice_que_hacer_antes_de_radicar(self, tmp_path):
        assert "antes de radicar" in _texto(SIN_FACTURADO, tmp_path)


class TestLaHomologacionSeAvisaEnPantalla:
    def test_se_ve_que_el_codigo_no_es_el_mismo(self, tmp_path):
        ev = dict(COMPLETO)
        ev["homologacion"] = {
            "aplicada": True,
            "codigo_entrada": "39147B-18",
            "cups_oficial": "39147",
            "norma": "Res. 2641/2025 MinSalud — CUPS 2025",
        }
        txt = _texto(ev, tmp_path)
        assert "pasó por una homologación" in txt
        assert "39147B-18" in txt and "39147" in txt


class TestElPanelNoEstorbaCuandoNoAplica:
    @pytest.mark.parametrize("ev", [None, {}, {"fila_del_catalogo": None}])
    def test_no_pinta_nada(self, ev, tmp_path):
        """La mayoría de las glosas no son de tarifas: un recuadro vacío en
        todas ellas sería ruido."""
        assert _pintar(ev, tmp_path).strip() == ""


class TestSinBasuraEnPantalla:
    @pytest.mark.parametrize("ev", [COMPLETO, SIN_FACTURADO, COINCIDE])
    def test_ni_undefined_ni_nan(self, ev, tmp_path):
        html = _pintar(ev, tmp_path)
        for basura in ("undefined", "NaN", "[object Object]"):
            assert basura not in html, f"Sale «{basura}» en pantalla."


class TestLaEvidenciaVaAntesDelVeredicto:
    def test_se_pinta_antes_del_riesgo_y_la_recomendacion(self):
        """Si el auditor lee primero la conclusión, ya no revisa la evidencia.
        El orden en la pantalla es parte del arreglo."""
        pagina = INDEX.read_text(encoding="utf-8", errors="ignore")
        i_ev = pagina.index("+ renderEvidenciaTarifa(d.evidencia_tarifa)")
        i_riesgo = pagina.index(
            "renderRiesgoRatificacion(d.riesgo_ratificacion) : '')", i_ev - 3000
        )
        i_accion = pagina.index("renderAccionIA(d) : '')", i_ev - 3000)
        assert i_ev < i_riesgo and i_ev < i_accion, (
            "La evidencia se pinta después del veredicto: el auditor lee la "
            "conclusión primero y ya no revisa el renglón del contrato."
        )
