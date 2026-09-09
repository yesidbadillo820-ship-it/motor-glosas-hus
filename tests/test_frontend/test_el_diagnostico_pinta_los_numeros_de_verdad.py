"""El panel del diagnóstico se EJECUTA, no solo se lee.

09-09-2026. Las otras pruebas de esta pantalla leen el `index.html` como
texto: comprueban que el panel esté, que llame a la ruta con el token, que
avise cuando falla. Todo eso puede estar bien y el panel salir en pantalla
con «undefined» donde va el porcentaje — que es justo el defecto que un
auditor sí nota y una prueba de texto no ve nunca. (La lección ya la dejó
escrita el 20-08: 89 pruebas de frontend en verde con el portal caído por
una llave de más.)

Esta corre el código de verdad con Node, contra una respuesta con la forma
exacta que devuelve `GET /admin/diagnostico-calidad`, y revisa dos cosas:
que los números lleguen a la pantalla y que no salga ni un «undefined» ni un
«NaN». Incluye la base recién instalada, sin una sola glosa, que es el caso
que más se rompe.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"

# La forma exacta de la respuesta del endpoint, con números realistas.
RESPUESTA = {
    "glosas_analizadas": 143,
    "eps": {
        "genericas": 61,
        "pct_genericas": 42.7,
        "con_nombre_real": [
            {"eps": "COOSALUD EPS", "glosas": 34},
            {"eps": "FAMISANAR", "glosas": 21},
        ],
    },
    "tarifas_pactadas_por_cups": {"filas": 0, "diagnostico": "VACÍA — no puede comparar por ítem."},
    "contratos": {"eps_con_clausulas": 4, "eps_con_registro_de_contrato": 7},
    "veredicto_final_eps": {
        "con_veredicto": 12,
        "pct": 8.4,
        "por_estado": [{"estado": "PENDIENTE", "glosas": 131}],
        "diagnostico": "Menos del 30%: el precedente se queda sin combustible.",
    },
    # 09-09-2026: `confianza_por_modelo` pasó de lista a objeto cuando se
    # separó la Confianza de verdad de la fórmula vieja de probabilidad de
    # éxito, que hasta entonces salían con el mismo nombre.
    "confianza_por_modelo": {
        "glosas_con_confianza_guardada": 128,
        "de_un_total_de": 143,
        "detalle": [
            {
                "modelo": "openai/gpt-oss-120b",
                "glosas": 120,
                "confianza_promedio": 41.2,
                "peor": 22.0,
                "mejor": 66.0,
            },
            {
                "modelo": "claude-sonnet-4-5",
                "glosas": 8,
                "confianza_promedio": 73.5,
                "peor": 58.0,
                "mejor": 89.0,
            },
        ],
        "diagnostico": "Esta es la comparación buena.",
    },
    "probabilidad_exito_por_modelo": [
        {"modelo": "openai/gpt-oss-120b", "glosas": 120, "promedio": 77.0},
    ],
    "costo_ia": [
        {
            "proveedor": "anthropic",
            "llamadas": 8,
            "costo_total_usd": 0.4312,
            "costo_promedio_usd": 0.0539,
            "latencia_promedio_ms": 4210,
            "proyeccion_mensual_usd_a_este_volumen": 7.71,
        }
    ],
}


@pytest.fixture(autouse=True)
def _hay_node():
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")


def _pintar(datos: dict, tmp_path: Path) -> str:
    """Corre de verdad el pintor del panel y devuelve el HTML que produce."""
    pagina = INDEX.read_text(encoding="utf-8", errors="ignore")
    try:
        ini = pagina.index("function _diagBloque(")
        fin = pagina.index("// ─── TEST SENTRY (solo SUPER_ADMIN)")
    except ValueError:  # pragma: no cover
        pytest.fail("No se encontró el pintor del diagnóstico en la página.")
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
    assert r.returncode == 0, f"El panel reventó al pintarse:\n{r.stderr}"
    return r.stdout


class TestLosNumerosLleganAPantalla:
    @pytest.mark.parametrize(
        "dato,que_es",
        [
            ("42.7", "el % de glosas sin entidad identificada"),
            ("COOSALUD EPS", "la EPS con más glosas"),
            ("8.4", "el % con veredicto final de la EPS"),
            ("41.2", "la confianza promedio del modelo que redacta hoy"),
            ("73.5", "la confianza promedio del otro modelo — la comparación clave"),
            ("claude-sonnet-4-5", "el nombre del modelo comparado"),
            ("7.71", "la proyección de costo mensual"),
        ],
    )
    def test_cada_cifra_se_ve(self, dato, que_es, tmp_path):
        html = _pintar(RESPUESTA, tmp_path)
        assert dato in html, f"No sale en pantalla {que_es} ({dato})."

    def test_no_sale_ni_un_undefined(self, tmp_path):
        html = _pintar(RESPUESTA, tmp_path)
        for basura in ("undefined", "NaN", "[object Object]"):
            assert basura not in html, (
                f"El panel muestra «{basura}» en pantalla. El auditor lo lee como "
                "un dato del hospital."
            )


class TestLosCasosQueMasSeRompen:
    def test_una_base_recien_instalada_sin_glosas(self, tmp_path):
        html = _pintar(
            {"glosas_analizadas": 0, "nota": "No hay glosas registradas todavía."},
            tmp_path,
        )
        assert "undefined" not in html and "NaN" not in html
        assert "No hay glosas registradas" in html

    def test_sin_llamadas_a_la_ia_registradas(self, tmp_path):
        """El caso de HOY: Anthropic solo entra como respaldo, así que la
        tabla de costos está vacía. No puede quedar un hueco mudo."""
        datos = dict(RESPUESTA, costo_ia=[])
        html = _pintar(datos, tmp_path)
        assert "undefined" not in html
        assert "Costo real de la IA" in html
        assert "no hay llamadas" in html.lower()

    def test_una_respuesta_a_medias_no_tumba_el_panel(self, tmp_path):
        """Si el servidor devuelve menos secciones de las esperadas —versión
        vieja, error parcial— el panel pinta lo que hay y no revienta."""
        html = _pintar({"glosas_analizadas": 143}, tmp_path)
        assert "143" in html
        assert "undefined" not in html and "NaN" not in html
