"""En pantalla, el motivo con «//» se lee numerado; la caja de edición sigue cruda.

08-09-2026. Misma regla que el PDF del oficio de devolución: cada «//» es un
corte y la observación siguiente arranca con «2- », «3- »… Se aplica donde el
motivo SE LEE (historial). Donde SE ESCRIBE (la caja de auditar) el texto sigue
tal cual, con sus «//»: es el separador que el gestor necesita conservar.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PAGINA = RAIZ / "static" / "preauditoria.html"
TEXTO = PAGINA.read_text(encoding="utf-8")


def _script() -> str:
    return "\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", TEXTO, re.S))


def _fuente_de(nombre: str) -> str:
    m = re.search(r"function " + nombre + r"\([^)]*\)\s*\{", _script())
    assert m, f"no existe la función {nombre}"
    fin = re.search(r"\n\}\n", _script()[m.end() :])
    assert fin, f"no se encontró el cierre de {nombre}"
    return _script()[m.start() : m.end() + fin.end()]


def _correr(texto: str) -> str:
    """Ejecuta la formatearMotivo REAL de la página contra un texto."""
    if not shutil.which("node"):  # pragma: no cover
        pytest.skip("node no está instalado en este entorno")
    guion = "%s\n%s\nconsole.log(JSON.stringify(formatearMotivo(%s)));" % (
        _fuente_de("esc"),
        _fuente_de("formatearMotivo"),
        json.dumps(texto, ensure_ascii=False),
    )
    r = subprocess.run(
        ["node", "-e", guion], capture_output=True, text=True, timeout=30, encoding="utf-8"
    )
    assert r.returncode == 0, f"la función falló:\n{r.stderr[:600]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


class TestFormatearMotivo:
    def test_numera_y_separa_por_renglon(self):
        salida = _correr("//FALTA A // FALTA B // FALTA C")
        assert salida == "1- FALTA A<br><br>2- FALTA B<br><br>3- FALTA C"

    def test_una_sola_observacion_queda_tal_cual(self):
        assert _correr("Falta FURIPS") == "Falta FURIPS"

    def test_vacio_es_raya(self):
        assert _correr("") == "—"

    def test_no_duplica_el_numero_que_ya_puso_el_gestor(self):
        assert _correr("1- A // 2- B") == "1- A<br><br>2- B"

    def test_escapa_html_dentro_de_cada_observacion(self):
        """El texto del gestor no puede inyectar etiquetas; los <br> sí son del formato."""
        salida = _correr("VALOR < PACTADO // CUPS & TARIFA")
        assert "&lt;" in salida and "&amp;" in salida
        assert "<br><br>" in salida


class TestDondeSeAplica:
    def test_en_el_historial_se_lee_numerado(self):
        assert "formatearMotivo(e.motivo)" in TEXTO

    def test_la_caja_de_editar_sigue_cruda(self):
        """Ahí el gestor necesita ver y conservar sus «//»."""
        assert "esc(f.motivo_devolucion||f.observaciones||'')" in TEXTO


class TestSigueCompilando:
    def test_los_bloques_de_script_compilan(self, tmp_path):
        if not shutil.which("node"):  # pragma: no cover
            pytest.skip("node no está instalado en este entorno")
        bloques = [
            c
            for c in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", TEXTO, re.S)
            if c.strip()
        ]
        for i, cuerpo in enumerate(bloques):
            archivo = tmp_path / f"b{i}.js"
            archivo.write_text(cuerpo, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(archivo)], capture_output=True, text=True)
            assert r.returncode == 0, f"el bloque {i} no compila:\n{r.stderr}"
