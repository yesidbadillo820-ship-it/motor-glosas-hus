"""La pantalla del Auditor Forense avisa qué documentos NO leyó.

19-08-2026. La pantalla decía «✅ 5 soportes leídos» y nada más. Si la IA
contestaba «no encontré evidencia», el gestor no tenía cómo saber que habían
quedado 7 documentos sin abrir — entre ellos la epicrisis y la hoja de
administración de medicamentos.

Un «no hay soporte» sobre un expediente leído a medias hace que se acepte una
glosa que había que objetar. Por eso el aviso no es decorativo: es la
diferencia entre una respuesta que se puede creer y una que no.
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


def _aviso(data: dict) -> str:
    """Corre la `afAvisoOmitidos` REAL con Node."""
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")
    guion = (
        "function escHtml(s){ return String(s == null ? '' : s)"
        ".replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;'); }\n"
        + _fuente_de("afAvisoOmitidos", _html())
        + f"\nconsole.log(JSON.stringify(afAvisoOmitidos({json.dumps(data, ensure_ascii=False)})));"
    )
    r = subprocess.run(
        ["node", "-e", guion], capture_output=True, text=True, timeout=30, encoding="utf-8"
    )
    assert r.returncode == 0, f"la función falló:\n{r.stderr[:600]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


# El caso real de HUS468334: 12 soportes, 5 leídos, 7 sin abrir.
_REAL = {
    "soportes_indexados": 12,
    "soportes_usados": [
        "HEV_900006037_HUS468334.pdf",
        "FEV_900006037_HUS468334.pdf",
        "EPICRISIS HUS468334.pdf",
        "HOJA DE ADMINISTRACION DE MEDICAMENTOS HUS468334.pdf",
        "OPF_900006037_HUS468334.pdf",
    ],
    "soportes_omitidos": [
        {"nombre_archivo": "RIPS_900006037_HUS468334.json", "motivo": "no es un PDF"},
        {
            "nombre_archivo": "PDE_900006037_HUS468334.pdf",
            "motivo": "solo caben 5 documentos por consulta",
        },
        {
            "nombre_archivo": "RESULTADOSMSPS_900006037_HUS468334.pdf",
            "motivo": "solo caben 5 documentos por consulta",
        },
    ],
}


class TestElAviso:
    def test_se_muestra_cuando_quedaron_documentos_sin_leer(self):
        salida = _aviso(_REAL)
        assert salida, "no se avisó nada pese a que quedaron 3 documentos sin abrir"
        assert "NO leyó todo el expediente" in salida

    def test_nombra_cada_documento_que_no_abrio(self):
        salida = _aviso(_REAL)
        for nombre in ("RIPS_900006037_HUS468334.json", "PDE_900006037_HUS468334.pdf"):
            assert nombre in salida, f"no se nombra {nombre}"

    def test_dice_el_motivo_de_cada_uno(self):
        salida = _aviso(_REAL)
        assert "no es un PDF" in salida
        assert "solo caben 5 documentos por consulta" in salida

    def test_dice_cuantos_de_cuantos(self):
        salida = _aviso(_REAL)
        assert "12" in salida and "5" in salida

    def test_le_dice_al_gestor_que_no_acepte_la_glosa_a_ciegas(self):
        salida = _aviso(_REAL)
        assert "antes de aceptar la glosa" in salida

    def test_no_estorba_cuando_se_leyo_todo(self):
        completo = {
            "soportes_indexados": 2,
            "soportes_usados": ["HEV_1.pdf", "FEV_1.pdf"],
            "soportes_omitidos": [],
        }
        assert _aviso(completo) == ""

    def test_una_respuesta_vieja_sin_el_campo_no_revienta(self):
        """El motor puede estar por actualizar: la pantalla no debe romperse."""
        assert _aviso({"soportes_usados": ["HEV_1.pdf"]}) == ""

    def test_los_nombres_van_escapados(self):
        salida = _aviso(
            {
                "soportes_indexados": 1,
                "soportes_usados": [],
                "soportes_omitidos": [
                    {"nombre_archivo": "<script>x</script>.pdf", "motivo": "no es un PDF"}
                ],
            }
        )
        assert "<script>" not in salida


class TestEstaConectadoDondeSeUsa:
    def test_el_recuadro_del_dictamen_muestra_el_aviso(self):
        """Es el único forense que queda: si él no avisa, nadie avisa."""
        texto = _html()
        m = re.search(r"async function auditarForense\(factura, rndId\)\{.*?\n\}\n", texto, re.S)
        assert m, "no se encontró auditarForense en index.html"
        assert "afAvisoOmitidos(data)" in m.group(0), (
            "el recuadro forense del dictamen no avisa qué documentos quedaron sin leer"
        )

    def test_el_backend_manda_los_campos_que_la_pantalla_espera(self):
        router = (RAIZ / "app" / "api" / "routers" / "auditor_forense.py").read_text(
            encoding="utf-8"
        )
        assert '"soportes_omitidos"' in router
        assert '"soportes_indexados"' in router


class TestElApartadoDuplicadoYaNoEsta:
    """19-08-2026. Yesid: «quitar ese apartado, no tendría sentido tener dos
    cosas que hacen exactamente lo mismo».

    El Auditor Forense vivía en dos sitios: un botón propio en HERRAMIENTAS y
    un recuadro dentro del dictamen. Se quedó el del dictamen, que es donde el
    gestor está trabajando cuando necesita mirar los soportes.

    Estas pruebas existen por la lección de «Salud Total»: aquella pantalla
    estuvo tres meses dando «Not Found» porque se borró el router y el
    JavaScript siguió llamándolo. Borrar de verdad es borrar TODO.
    """

    def test_no_queda_el_boton_del_menu(self):
        assert "sidebarTab(this,'auditor-forense')" not in _html()

    def test_no_queda_el_panel(self):
        assert 'id="p-auditor-forense"' not in _html()

    def test_no_quedan_funciones_llamando_a_una_pantalla_que_ya_no_existe(self):
        texto = _html()
        for fn in (
            "auditorForenseStandalone",
            "auditorForenseDesdeServidorLocal",
            "guardarUrlServidorLocal",
            "probarServidorLocal",
            "importarRutasCsv",
            "_afCargarServerUrlEnInput",
            "_afOnFacturaChange",
            "copiarAFOut",
            "descargarAFOut",
        ):
            assert fn not in texto, f"{fn} quedó suelta apuntando al panel borrado"

    def test_no_quedan_campos_huerfanos_del_panel(self):
        texto = _html()
        for campo in ("af-factura", "af-pregunta", "af-out", "af-server-url", "af-setup-pill"):
            assert campo not in texto, f"quedó el campo {campo} del panel borrado"

    def test_el_buscador_del_menu_lleva_a_analizar_glosa(self):
        """Quien escriba «forense» en el buscador debe llegar a donde vive."""
        texto = _html()
        assert "'auditor forense':'analizar'" in texto
        assert "'auditor-forense'" not in texto

    def test_el_recuadro_dentro_del_dictamen_sigue_en_pie(self):
        texto = _html()
        assert "function renderAuditorForensePanel(" in texto
        assert "renderAuditorForensePanel(d)" in texto, "ya no se pinta en el dictamen"

    def test_la_ruta_del_backend_sigue_viva_porque_el_dictamen_la_usa(self):
        """Lo contrario del caso «Salud Total»: acá el JS SIGUE llamando."""
        assert "fetch('/auditor-forense/'" in _html()
        router = RAIZ / "app" / "api" / "routers" / "auditor_forense.py"
        assert router.exists()
        assert 'APIRouter(prefix="/auditor-forense"' in router.read_text(encoding="utf-8")
