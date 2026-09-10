"""La pantalla de Analizar acompaña al gestor, no le tira un formulario.

10-09-2026. Yesid lo pidió con estas palabras: «que no se comporte como un
formulario automatizado; que actúe como un compañero de equipo que guía el
análisis paso a paso». Y puso tres reglas duras:

  1. Un dato a la vez. Nunca la plantilla completa de golpe.
  2. Cero suposiciones: lo que el gestor no dijo, no se inventa.
  3. Dictamen pausado: no se analiza NADA hasta terminar de recoger.

Estas pruebas EJECUTAN el guion con Node contra estados reales, en vez de
leer el `index.html` como texto. La lección ya está escrita en la bitácora
del 20-08: 89 pruebas de frontend en verde con el portal caído.
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


def _guion(pagina: str) -> str:
    """El trozo de la guía, con las dos ayudas que usa del resto de la página."""
    try:
        ini = pagina.index("var PA_GUIA = { i: 0, datos: {}, arrancada: false };")
        fin = pagina.index("// ─── CONTRATOS ───")
    except ValueError:  # pragma: no cover
        pytest.fail("No se encontró la guía conversacional en la página.")
    ayudas = (
        "function escHtml(v){if(v===null||v===undefined)return '';"
        "return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        "function fmtCOP(n){return '$ ' + Number(n||0).toLocaleString('es-CO');}\n"
    )
    return ayudas + pagina[ini:fin]


def _correr(expresion: str, tmp_path: Path) -> str:
    pagina = INDEX.read_text(encoding="utf-8", errors="ignore")
    guion = tmp_path / "guia.mjs"
    guion.write_text(
        _guion(pagina) + "\nprocess.stdout.write(String(" + expresion + "));\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        ["node", str(guion)], capture_output=True, text=True, timeout=30, check=False
    )
    assert r.returncode == 0, f"La guía reventó:\n{r.stderr}"
    return r.stdout


def _hilo(estado: dict, tmp_path: Path) -> str:
    return _correr("paGuiaPintarHilo(" + json.dumps(estado, ensure_ascii=False) + ")", tmp_path)


def _resumen(datos: dict, tmp_path: Path) -> str:
    return _correr("paGuiaPintarResumen(" + json.dumps(datos, ensure_ascii=False) + ")", tmp_path)


def _avisos(datos: dict, tmp_path: Path) -> list:
    salida = _correr(
        "JSON.stringify(paGuiaAvisos(" + json.dumps(datos, ensure_ascii=False) + "))", tmp_path
    )
    return json.loads(salida)


class TestUnDatoALaVez:
    """La regla 1: nunca la plantilla completa."""

    def test_al_arrancar_solo_se_ve_la_primera_pregunta(self, tmp_path):
        html = _hilo({"i": 0, "datos": {}}, tmp_path)
        assert "¿Qué EPS o entidad nos está glosando?" in html
        for despues in ("número de factura", "concepto de la glosa", "las dos fechas"):
            assert despues.lower() not in html.lower(), (
                f"Se adelantó y ya preguntó por «{despues}» en el primer paso: eso es un formulario."
            )

    def test_cada_paso_muestra_solo_una_pregunta_pendiente(self, tmp_path):
        pasos = json.loads(_correr("JSON.stringify(paGuiaPasos().map(p=>p.pregunta))", tmp_path))
        for i in range(len(pasos)):
            html = _hilo({"i": i, "datos": {}}, tmp_path)
            pendientes = [p for p in pasos[i:] if p in html]
            assert len(pendientes) == 1, (
                f"En el paso {i} hay {len(pendientes)} preguntas sin responder a la vista: {pendientes}"
            )

    def test_son_los_datos_que_pidio_el_auditor(self, tmp_path):
        ids = json.loads(_correr("JSON.stringify(paGuiaPasos().map(p=>p.id))", tmp_path))
        assert ids == ["eps", "etapa", "fechas", "factura", "valor", "texto", "soportes"]


class TestCeroSuposiciones:
    """La regla 2: lo que no dijo el gestor, no se inventa."""

    def test_un_dato_saltado_se_ve_como_pendiente_no_como_un_valor(self, tmp_path):
        html = _hilo(
            {"i": 3, "datos": {"_eco_eps": "COOSALUD", "_eco_etapa": "Respuesta inicial"}}, tmp_path
        )
        assert "lo dejamos pendiente" in html

    def test_el_resumen_dice_sin_dato_donde_no_hay_dato(self, tmp_path):
        html = _resumen({"eps": "COOSALUD", "etapa": "INICIAL"}, tmp_path)
        assert "sin dato" in html
        for basura in ("undefined", "NaN", "null", "[object Object]"):
            assert basura not in html, f"El resumen muestra «{basura}» donde el gestor lee un dato."

    def test_sin_valor_aceptado_muestra_cero_no_un_invento(self, tmp_path):
        html = _resumen({"eps": "SURA"}, tmp_path)
        assert "$ 0" in html


class TestLasPreguntasCortasDeValidacion:
    """La regla 3: preguntar lo que no cuadra, sin sacar conclusiones."""

    def test_avisa_si_la_glosa_llego_antes_de_radicar_la_factura(self, tmp_path):
        avisos = _avisos(
            {"f_rad": "2026-05-10", "f_rec": "2026-04-02", "factura": "X", "texto": "x" * 60},
            tmp_path,
        )
        assert any("antes de radicada" in a["txt"].lower() for a in avisos)

    def test_no_avisa_cuando_las_fechas_van_en_orden(self, tmp_path):
        avisos = _avisos(
            {"f_rad": "2026-04-02", "f_rec": "2026-05-10", "factura": "X", "texto": "x" * 60},
            tmp_path,
        )
        assert not any("antes de radicada" in a["txt"].lower() for a in avisos)

    def test_avisa_cuando_faltan_las_fechas(self, tmp_path):
        avisos = _avisos({"factura": "X", "texto": "x" * 60}, tmp_path)
        assert any("extempor" in a["txt"].lower() for a in avisos)

    def test_avisa_cuando_falta_la_factura(self, tmp_path):
        avisos = _avisos(
            {"f_rad": "2026-04-02", "f_rec": "2026-05-10", "texto": "x" * 60}, tmp_path
        )
        assert any("factura" in a["txt"].lower() for a in avisos)

    def test_pregunta_si_el_concepto_quedo_muy_corto(self, tmp_path):
        avisos = _avisos(
            {"f_rad": "2026-04-02", "f_rec": "2026-05-10", "factura": "X", "texto": "TA0201"},
            tmp_path,
        )
        assert any("todo lo que mandó" in a["txt"] for a in avisos)

    def test_un_caso_completo_no_genera_ni_un_aviso(self, tmp_path):
        avisos = _avisos(
            {
                "f_rad": "2026-04-02",
                "f_rec": "2026-05-10",
                "factura": "HUS0000541440",
                "texto": "TA0201 TARIFAS. Se objeta mayor valor cobrado frente a la tarifa pactada.",
            },
            tmp_path,
        )
        assert avisos == []

    def test_la_guia_no_declara_extemporanea_por_su_cuenta(self, tmp_path):
        """Los días hábiles los cuenta el motor, que tiene los festivos.

        Si la guía se pusiera a dictaminar acá, contradiría a
        `extemporaneidad_texto.py` el día que las dos cuentas no coincidan.
        """
        avisos = _avisos(
            {"f_rad": "2026-01-02", "f_rec": "2026-11-30", "factura": "X", "texto": "x" * 60},
            tmp_path,
        )
        textos = " ".join(a["txt"].upper() for a in avisos)
        assert "ES EXTEMPORÁNEA" not in textos
        assert "IMPROCEDENTE" not in textos


class TestElDictamenEsperaATenerTodo:
    """La regla 4: no se analiza hasta terminar de recoger."""

    def test_el_boton_de_analizar_no_aparece_a_mitad_de_camino(self, tmp_path):
        for i in range(6):
            html = _hilo({"i": i, "datos": {}}, tmp_path)
            assert "paGuiaLanzar()" not in html, f"El paso {i} ya ofrece analizar sin tener todo."

    def test_el_resumen_llega_antes_del_analisis(self, tmp_path):
        html = _resumen(
            {"eps": "COOSALUD", "etapa": "INICIAL", "factura": "X", "texto": "y" * 60}, tmp_path
        )
        assert "Revíselo antes" in html


class TestNoSePierdeElFormularioDeSiempre:
    def _codigo(self) -> str:
        """El HTML sin los renglones de comentario, para no medirme a mí mismo."""
        lineas = INDEX.read_text(encoding="utf-8", errors="ignore").split("\n")
        return "\n".join(ln for ln in lineas if not ln.strip().startswith(("//", "<!--", "*")))

    def test_el_formulario_clasico_sigue_estando(self):
        t = self._codigo()
        assert 'id="pa-form-clasico"' in t
        assert "paCambiarModo('form')" in t

    def test_la_guia_escribe_en_los_campos_de_siempre(self):
        """Si la guía guardara los datos aparte, el análisis saldría vacío."""
        t = self._codigo()
        for campo in (
            "eps-sel",
            "etapa-v",
            "f-rad",
            "f-rec",
            "f-factura",
            "f-radicado",
            "f-valacp",
            "f-glosa",
        ):
            assert "_set('" + campo + "'" in t, f"La guía no llena {campo}"

    def test_dispara_el_mismo_analisis_de_siempre(self):
        assert "if(typeof analizar === 'function') analizar();" in self._codigo()


class TestSeLeeEnLosDosTemas:
    """El color no se eligió a ojo: se midió en pantalla.

    Con `--sds-blue-500` (#1E88E5) el blanco encima daba 3,68:1 y el mínimo
    legible es 4,5:1 — y esas burbujas son las respuestas del propio gestor,
    que tiene que poder releerlas. El 700 da 5,75:1.

    Y la burbuja del motor NO puede usar los grises fijos del sistema de
    diseño: `--sds-gray-50` es #F5F7FA y el fondo del motor en tema claro es
    #F8FAFC. El mismo color: la burbuja desaparecía. Usa las variables del
    motor, que sí cambian con el tema, más un borde que la delinea siempre.
    """

    def _css(self) -> str:
        t = INDEX.read_text(encoding="utf-8", errors="ignore")
        return t[t.index(".pa-modos{") : t.index("@media (max-width:640px){.pa-hilo")]

    def test_la_burbuja_del_gestor_tiene_contraste_suficiente(self):
        css = self._css()
        assert "background:var(--sds-blue-700)" in css, (
            "La respuesta del gestor volvió a un azul con menos de 4,5:1 de contraste."
        )

    def test_la_burbuja_del_motor_sigue_el_tema(self):
        css = self._css()
        assert "background:var(--bg-card" in css
        assert "border:1px solid var(--border" in css, (
            "Sin borde, la burbuja se pierde: su fondo y el de la página son casi el mismo color."
        )

    def test_ningun_gris_fijo_en_la_guia(self):
        """Los grises del sistema de diseño no cambian con el tema."""
        for regla in self._css().split("}"):
            if regla.strip().startswith(".pa-") and "sds-gray" in regla:
                raise AssertionError(f"Gris fijo en una regla de la guía: {regla.strip()[:90]}")
