"""El JavaScript de la página tiene que COMPILAR, no solo contener frases.

20-08-2026. Al quitar el panel de Agentes quedó una llave de cierre suelta en
`static/index.html:9390`. El navegador reportó:

    Uncaught SyntaxError: Unexpected token '}'   (index):9390
    Uncaught ReferenceError: doLogin is not defined

Un error de sintaxis **anula el bloque entero de JavaScript**. Ninguna función
queda definida, así que el botón «Ingresar» no hacía nada: ni mensaje, ni giro,
ni error. Yesid quedó sin poder entrar al portal y sin una sola pista.

**Y las 89 pruebas de frontend pasaban.** Todas leen el HTML como texto: buscan
que ciertas cadenas estén presentes, no que el programa funcione. Comprobar que
un texto está no es comprobar que algo sirve — y eso costó el portal.
"""

from __future__ import annotations

import re
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


def _bloques_inline() -> list[str]:
    """Los <script> escritos dentro de la página (los que no traen `src`)."""
    if not INDEX.exists():  # pragma: no cover
        pytest.skip("static/index.html no está en este entorno")
    texto = INDEX.read_text(encoding="utf-8", errors="ignore")
    return [
        c
        for c in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", texto, re.S)
        if c.strip()
    ]


def _compila(codigo: str, tmp_path: Path, nombre: str = "bloque.js"):
    archivo = tmp_path / nombre
    archivo.write_text(codigo, encoding="utf-8")
    return subprocess.run(
        ["node", "--check", str(archivo)],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )


class TestLaPaginaCompila:
    def test_todos_los_bloques_de_script_compilan(self, tmp_path):
        bloques = _bloques_inline()
        assert bloques, "no se encontró ningún <script> en la página"
        for i, cuerpo in enumerate(bloques):
            r = _compila(cuerpo, tmp_path, f"b{i}.js")
            assert r.returncode == 0, (
                f"el bloque <script> #{i + 1} NO compila — la página entera se queda "
                f"sin JavaScript:\n{r.stderr[:700]}"
            )

    def test_los_archivos_js_sueltos_tambien_compilan(self, tmp_path):
        for js in sorted((RAIZ / "static").glob("*.js")):
            r = subprocess.run(
                ["node", "--check", str(js)],
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
                errors="replace",
            )
            assert r.returncode == 0, f"{js.name} no compila:\n{r.stderr[:500]}"


class TestElBotonDeIngresar:
    """La regresión exacta: el botón llamaba a `doLogin`, que había dejado de
    existir porque el bloque entero no compilaba."""

    def test_el_boton_llama_a_una_funcion_que_existe(self):
        texto = INDEX.read_text(encoding="utf-8", errors="ignore")
        assert "doLogin()" in texto, "el botón de login perdió su llamada"
        assert "function doLogin" in texto, "doLogin dejó de estar definida"

    def test_avisa_cuando_hay_demasiados_intentos(self):
        """Un 429 decía «Credenciales incorrectas» y encerraba al auditor."""
        texto = INDEX.read_text(encoding="utf-8", errors="ignore")
        assert "r.status === 429" in texto
        assert "Su clave puede estar bien" in texto


class TestNoQuedanLlavesHuerfanas:
    def test_ninguna_llave_sola_despues_de_otra(self):
        """Lo que dejó el borrado del panel de Agentes: un `}` sin nada que
        cerrar, separado del anterior solo por comentarios y líneas vacías."""
        lineas = INDEX.read_text(encoding="utf-8", errors="ignore").splitlines()
        sospechosas = []
        for i, ln in enumerate(lineas):
            if ln.strip() != "}":
                continue
            j = i - 1
            while j >= 0 and (not lineas[j].strip() or lineas[j].lstrip().startswith("//")):
                j -= 1
            if j >= 0 and lineas[j].strip() == "}":
                if any(not lineas[k].strip() for k in range(j + 1, i)):
                    sospechosas.append(i + 1)
        assert not sospechosas, f"llaves posiblemente huérfanas en las líneas {sospechosas}"
