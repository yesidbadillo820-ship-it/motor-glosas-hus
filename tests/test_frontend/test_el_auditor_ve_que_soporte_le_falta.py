"""El panel de soportes se EJECUTA, no solo se lee.

09-09-2026. La otra mitad de «que vean qué van a auditar». Esta prueba corre
el pintor de verdad con Node contra las formas que devuelve el motor, porque
buscar cadenas en el HTML diría que todo está bien aunque en pantalla saliera
«undefined» donde va el documento que falta.
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

FALTA = {
    "factura": "HUS0000549713",
    "codigo_glosa": "SO0101",
    "pide_la_causal": [
        {"tipo": "epicrisis", "nombre": "la epicrisis"},
        {"tipo": "hoja_atencion_urgencias", "nombre": "la hoja de atención de urgencias"},
    ],
    "hay_en_el_expediente": [],
    "se_adjunto_en_este_analisis": [],
    "faltan": ["la epicrisis", "la hoja de atención de urgencias"],
    "no_se_pudo_consultar": False,
}

ESTA = {
    "factura": "HUS0000549713",
    "codigo_glosa": "SO0101",
    "pide_la_causal": [{"tipo": "epicrisis", "nombre": "la epicrisis"}],
    "hay_en_el_expediente": [
        {"tipo": "epicrisis", "nombre": "la epicrisis", "archivo": "EPICRISIS_549713.pdf"}
    ],
    "se_adjunto_en_este_analisis": ["epicrisis_firmada.pdf"],
    "faltan": [],
    "no_se_pudo_consultar": False,
}

RECONSTRUYENDO = {
    "factura": "HUS0000549713",
    "codigo_glosa": "SO0701",
    "pide_la_causal": [{"tipo": "historia_clinica", "nombre": "la historia clínica"}],
    "hay_en_el_expediente": [],
    "se_adjunto_en_este_analisis": [],
    "faltan": [],
    "no_se_pudo_consultar": True,
}


@pytest.fixture(autouse=True)
def _hay_node():
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")


def _pintar(ev, tmp_path: Path) -> str:
    pagina = INDEX.read_text(encoding="utf-8", errors="ignore")
    ini = pagina.index("function renderEvidenciaSoportes(")
    fin = pagina.index("// ─── LA EVIDENCIA DE LA TARIFA")
    guion = tmp_path / "sop.mjs"
    guion.write_text(
        "function escHtml(v){if(v===null||v===undefined)return '';"
        "return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        + pagina[ini:fin]
        + "\nprocess.stdout.write(renderEvidenciaSoportes("
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
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _pintar(ev, tmp_path)))


class TestCuandoFaltaElSoporte:
    def test_dice_cual_falta_por_su_nombre(self, tmp_path):
        txt = _texto(FALTA, tmp_path)
        assert "la epicrisis" in txt

    def test_explica_lo_que_cuesta(self, tmp_path):
        """«Falta la epicrisis» sin consecuencia se ignora."""
        txt = _texto(FALTA, tmp_path)
        assert "argumenta, pero no prueba" in txt
        assert "ratificar la glosa" in txt

    def test_dice_que_hacer(self, tmp_path):
        assert "antes de radicar" in _texto(FALTA, tmp_path)

    def test_se_ve_que_exige_la_causal(self, tmp_path):
        txt = _texto(FALTA, tmp_path)
        assert "SO0101" in txt


class TestCuandoElSoporteEsta:
    def test_se_lista_con_su_archivo(self, tmp_path):
        """El nombre del archivo es lo que permite ir a abrirlo."""
        assert "EPICRISIS_549713.pdf" in _texto(ESTA, tmp_path)

    def test_se_ve_lo_adjuntado_en_este_analisis(self, tmp_path):
        assert "epicrisis_firmada.pdf" in _texto(ESTA, tmp_path)

    def test_dice_que_hay_que_nombrarlo_en_el_escrito(self, tmp_path):
        """Tenerlo no basta: si el dictamen no lo señala, la entidad pide el
        folio y ratifica igual."""
        txt = _texto(ESTA, tmp_path)
        assert "folio" in txt

    def test_no_dice_que_falta_nada(self, tmp_path):
        assert "Falta" not in _texto(ESTA, tmp_path)


class TestTodaviaNoSeNoEsNoHay:
    def test_se_distingue_del_expediente_vacio(self, tmp_path):
        txt = _texto(RECONSTRUYENDO, tmp_path)
        assert "Todavía no se sabe" in txt
        assert "a medio armar" in txt

    def test_NO_acusa_de_que_falte_nada(self, tmp_path):
        txt = _texto(RECONSTRUYENDO, tmp_path)
        assert "argumenta, pero no prueba" not in txt, (
            "Acusa de faltar soportes mientras el índice se reconstruye. Esa "
            "factura puede tener el expediente completo."
        )

    def test_dice_que_hacer_para_saberlo(self, tmp_path):
        assert "vuelva a analizar" in _texto(RECONSTRUYENDO, tmp_path)


class TestNoEstorbaCuandoNoAplica:
    @pytest.mark.parametrize(
        "ev",
        [
            None,
            {
                "factura": "X",
                "codigo_glosa": "TA0201",
                "pide_la_causal": [],
                "hay_en_el_expediente": [],
                "se_adjunto_en_este_analisis": [],
                "faltan": [],
                "no_se_pudo_consultar": False,
            },
        ],
    )
    def test_no_pinta_nada(self, ev, tmp_path):
        assert _pintar(ev, tmp_path).strip() == ""


class TestSinBasuraEnPantalla:
    @pytest.mark.parametrize("ev", [FALTA, ESTA, RECONSTRUYENDO])
    def test_ni_undefined_ni_nan(self, ev, tmp_path):
        html = _pintar(ev, tmp_path)
        for basura in ("undefined", "NaN", "[object Object]"):
            assert basura not in html, f"Sale «{basura}» en pantalla."


class TestVaAntesDelVeredicto:
    def test_se_pinta_junto_a_la_evidencia_de_tarifa(self):
        """Misma razón que con las tarifas: si el auditor lee primero la
        conclusión, ya no revisa la evidencia."""
        pagina = INDEX.read_text(encoding="utf-8", errors="ignore")
        i_sop = pagina.index("+ renderEvidenciaSoportes(d.evidencia_soportes)")
        i_riesgo = pagina.index(
            "renderRiesgoRatificacion(d.riesgo_ratificacion) : '')", i_sop - 3000
        )
        assert i_sop < i_riesgo
