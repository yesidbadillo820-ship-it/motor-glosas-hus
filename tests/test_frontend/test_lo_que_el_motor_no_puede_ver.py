"""El motor decía «está el soporte que la causal exige» y era falso.

10-09-2026. Caso real: objeción N° 189801, causal **SO4201 — ausencia o
inconsistencia de LISTA DE PRECIOS**, por $55.882.100.

El mapa de soportes no tenía esa causal, así que caía en la regla general de
la familia SO y le pedía **historia clínica y epicrisis**. Las dos estaban en
el expediente, así que el panel se pintaba VERDE y concluía:

    «Está el soporte que la causal exige.»

Falso. Lo que el Dispensario pedía, textual y siete veces, era otra cosa:

    «NO SE EVIDENCIA FRA DE COMPRA Y COTIZACIÓN AVALADA POR SANIDAD MILITAR»

Ni la historia clínica ni la epicrisis prueban una lista de precios.

LO GRAVE NO ES QUE FALTARA EL DATO: es que el motor daba una **tranquilidad
falsa** sobre cincuenta y cinco millones. Con un «esto no lo puedo ver» el
auditor va y lo busca; con un «está el soporte» radica confiado y la entidad
ratifica sin más que volver a pedir el documento.

El indexador solo reconoce documentos clínicos y de facturación. Una lista de
precios, una factura de compra o una cotización avalada no están en su
vocabulario — y eso hay que DECIRLO, no taparlo con el primer documento que
haya a mano.
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


def _pintar(ev: dict, tmp_path: Path) -> str:
    pagina = INDEX.read_text(encoding="utf-8", errors="ignore")
    ini = pagina.index("function renderEvidenciaSoportes(")
    fin = pagina.index("\nfunction ", ini + 10)
    guion = tmp_path / "p.mjs"
    guion.write_text(
        "function escHtml(v){if(v==null)return '';"
        "return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        + pagina[ini:fin]
        + "\nprocess.stdout.write(renderEvidenciaSoportes("
        + json.dumps(ev, ensure_ascii=False)
        + "));\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        ["node", str(guion)], capture_output=True, text=True, timeout=30, check=False
    )
    assert r.returncode == 0, f"el panel reventó:\n{r.stderr}"
    return r.stdout


# El caso real: la causal pide algo que el motor no indexa, y el expediente
# tiene documentos clínicos que NO prueban esa causal.
CASO_SO4201 = {
    "factura": "HUS0000541440",
    "codigo_glosa": "SO4201",
    "pide_la_causal": [],
    "pide_y_no_lo_veo": [
        "la lista de precios pactada (anexo tarifario del contrato)",
        "la factura de compra del material",
        "la cotización avalada por la entidad",
    ],
    "hay_en_el_expediente": [
        {"tipo": "historia_clinica", "nombre": "la historia clínica", "archivo": "HEV.pdf"},
        {"tipo": "epicrisis", "nombre": "la epicrisis", "archivo": "EPI.pdf"},
    ],
    "se_adjunto_en_este_analisis": [],
    "faltan": [],
    "no_se_pudo_consultar": False,
}


class TestElCasoQueLoDestapo:
    def test_ya_no_dice_que_el_soporte_esta(self, tmp_path):
        html = _pintar(CASO_SO4201, tmp_path)
        assert "Está el soporte que la causal exige" not in html, (
            "esa frase sobre $55.882.100 que nadie probó es la que hace radicar confiado"
        )

    def test_el_recuadro_no_sale_verde(self, tmp_path):
        """El verde dice «resuelto». Sobre lo que no se pudo mirar, eso miente."""
        assert "#10b981" not in _pintar(CASO_SO4201, tmp_path)

    def test_nombra_los_tres_documentos_que_de_verdad_piden(self, tmp_path):
        html = _pintar(CASO_SO4201, tmp_path)
        for doc in ("lista de precios", "factura de compra", "cotización avalada"):
            assert doc in html, f"no le dice al auditor que busque {doc}"

    def test_dice_que_es_el_motor_el_que_no_puede(self, tmp_path):
        """«No lo puedo ver» manda a buscar; «no está» acusa sin saber."""
        html = _pintar(CASO_SO4201, tmp_path)
        assert "no lo puede revisar por usted" in html

    def test_no_esconde_lo_que_si_hay_en_el_expediente(self, tmp_path):
        """La historia clínica sigue listándose; lo que cambia es la conclusión."""
        html = _pintar(CASO_SO4201, tmp_path)
        assert "historia clínica" in html


class TestLoQueSiEstaResueltoSigueEnVerde:
    """Si esto se cae, el arreglo se pasó y ahora todo da desconfianza."""

    def test_una_causal_con_su_soporte_presente(self, tmp_path):
        html = _pintar(
            {
                "factura": "HUS1",
                "codigo_glosa": "SO0101",
                "pide_la_causal": [{"tipo": "epicrisis", "nombre": "la epicrisis"}],
                "pide_y_no_lo_veo": [],
                "hay_en_el_expediente": [
                    {"tipo": "epicrisis", "nombre": "la epicrisis", "archivo": "EPI.pdf"}
                ],
                "se_adjunto_en_este_analisis": [],
                "faltan": [],
                "no_se_pudo_consultar": False,
            },
            tmp_path,
        )
        assert "Está el soporte que la causal exige" in html
        assert "#10b981" in html

    def test_una_causal_con_su_soporte_faltando_sigue_en_rojo(self, tmp_path):
        html = _pintar(
            {
                "factura": "HUS1",
                "codigo_glosa": "SO0101",
                "pide_la_causal": [{"tipo": "epicrisis", "nombre": "la epicrisis"}],
                "pide_y_no_lo_veo": [],
                "hay_en_el_expediente": [],
                "se_adjunto_en_este_analisis": [],
                "faltan": ["la epicrisis"],
                "no_se_pudo_consultar": False,
            },
            tmp_path,
        )
        assert "Falta la epicrisis" in html

    def test_el_indice_a_medio_armar_sigue_avisando(self, tmp_path):
        html = _pintar(
            {
                "factura": "HUS1",
                "codigo_glosa": "SO0101",
                "pide_la_causal": [{"tipo": "epicrisis", "nombre": "la epicrisis"}],
                "pide_y_no_lo_veo": [],
                "hay_en_el_expediente": [],
                "se_adjunto_en_este_analisis": [],
                "faltan": [],
                "no_se_pudo_consultar": True,
            },
            tmp_path,
        )
        assert "a medio armar" in html
