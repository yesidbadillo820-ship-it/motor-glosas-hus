"""La pantalla de pre-auditoría tiene que COMPILAR y verse ordenada.

25-08-2026. Yesid, textual: «hay mucho ruido visual, todos los botones ahí
todos juntos, sin nada de profesionalismo y estética, que es lo que nos debe
caracterizar». En la tabla de oficios los botones se apilaban en dos renglones,
de distinto alto, y el lápiz ✏ ni siquiera se dibujaba en el navegador del
hospital: salía una rayita.

La otra mitad de esta prueba es la red de seguridad que faltaba: la prueba que
compila el JavaScript solo miraba static/index.html, así que un error de
sintaxis en esta página —que se arma entera con cadenas de texto— dejaba la
pantalla muerta sin que ninguna prueba se enterara.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PAGINA = RAIZ / "static" / "preauditoria.html"


def _texto() -> str:
    return PAGINA.read_text(encoding="utf-8")


def _bloques() -> list[str]:
    return [
        c
        for c in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", _texto(), re.S)
        if c.strip()
    ]


class TestElJavaScriptCompila:
    """Un error de sintaxis anula TODO el JavaScript de la página: no hay
    tablas, no hay botones, no hay mensaje de error. Solo una pantalla muerta."""

    def test_los_bloques_de_script_compilan(self, tmp_path):
        if not shutil.which("node"):  # pragma: no cover
            pytest.skip("node no está instalado en este entorno")
        bloques = _bloques()
        assert bloques, "no se encontró ningún <script> en la página"
        for i, cuerpo in enumerate(bloques):
            archivo = tmp_path / f"b{i}.js"
            archivo.write_text(cuerpo, encoding="utf-8")
            r = subprocess.run(
                ["node", "--check", str(archivo)],
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
                errors="replace",
            )
            assert r.returncode == 0, (
                f"el bloque <script> #{i + 1} NO compila — la pantalla de "
                f"pre-auditoría se queda sin JavaScript:\n{r.stderr[:700]}"
            )


class TestLasAccionesDeCadaFila:
    def test_van_en_una_sola_barra_pareja(self):
        t = _texto()
        assert ".acciones{display:flex" in t, "no existe la barra de acciones"
        assert t.count('<div class="acciones">') >= 4, (
            "alguna tabla quedó con los botones sueltos: la pantalla queda dispareja"
        )
        # Cada barra abierta se cierra: si no, la tabla se desarma.
        assert t.count('<div class="acciones">') == t.count("'</div></td>")

    def test_el_lapiz_es_un_dibujo_y_no_un_emoji(self):
        """El ✏ (U+270F) no se dibuja en el navegador del hospital."""
        t = _texto()
        assert "var ICO_LAPIZ = '<svg" in t
        assert "corregirOficio(" in t and "'+ICO_LAPIZ+'" in t
        assert "'>✏</button>" not in t, "volvió el lápiz en emoji"

    def test_los_botones_de_solo_icono_dicen_qué_hacen(self):
        """Un botón sin palabras necesita título y etiqueta para quien no
        distingue el dibujo."""
        for boton in re.findall(r"<button[^>]*btn-ico[^>]*>", _texto()):
            assert "title=" in boton, f"botón de icono sin título: {boton[:120]}"
            assert "aria-label=" in boton, f"botón de icono sin etiqueta: {boton[:120]}"


class TestLaTablaSeLee:
    def test_los_numeros_van_alineados_a_la_derecha(self):
        t = _texto()
        assert "th.num, td.num{text-align:right" in t
        assert t.count('<th class="num">') >= 4, "los encabezados numéricos no están marcados"
        assert t.count('<td class="num"') >= 4, "las celdas numéricas no están marcadas"

    def test_la_columna_de_envios_no_estira_la_fila(self):
        """Un oficio con 20 envíos hacía la fila tres veces más alta."""
        t = _texto()
        assert "TOPE_ENV" in t, "no hay tope de envíos visibles"
        assert "más</span>" in t, "no dice cuántos envíos quedaron sin mostrar"
        assert "title=\"'+esc(lista.join(' '))+'\"" in t, "la lista completa no queda en el globo"
