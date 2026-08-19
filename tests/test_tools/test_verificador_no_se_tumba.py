"""El verificador de doble clic nunca le muestra un traceback al auditor.

19-08-2026. La primera vez que Yesid corrió `VERIFICAR_TRABAJO_HOY.cmd`, su PC
tenía el verificador NUEVO contra el código VIEJO —el autodeploy había bajado
los archivos a medias— y el programa se cerró escupiendo:

    Traceback (most recent call last):
      File "C:\\motor-glosas\\repo\\tools\\verificar_trabajo_hoy.py", line 292 ...
    ImportError: cannot import name 'aceptado_sin_duplicar' from ...

Un bot de doble clic para Cartera no puede hacer eso. El auditor no sabe qué
es un ImportError, no sabe si perdió trabajo, y no sabe qué hacer después. Y
peor: una sola revisión rota tumbaba las otras tres, que sí se podían hacer.

Ahora cada revisión corre aparte: si falta código, se dice en castellano qué
pasó y qué hacer, y las demás siguen.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
GUION = RAIZ / "tools" / "verificar_trabajo_hoy.py"


def _correr(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(cwd / "tools" / "verificar_trabajo_hoy.py")],
        capture_output=True,
        text=True,
        input="",
        cwd=str(cwd),
        timeout=180,
        encoding="utf-8",
        errors="replace",
    )


def _pc_desactualizado(tmp_path: Path) -> Path:
    """Copia el repo y le quita la función nueva, como estaba el PC de Yesid."""
    import shutil

    destino = tmp_path / "repo"
    for carpeta in ("tools", "app", "static"):
        shutil.copytree(RAIZ / carpeta, destino / carpeta, dirs_exist_ok=True)
    viejo = destino / "tools" / "glosas_adres_por_factura.py"
    viejo.write_text(
        viejo.read_text(encoding="utf-8").replace(
            "def aceptado_sin_duplicar", "def _no_existe_todavia"
        ),
        encoding="utf-8",
    )
    return destino


class TestConElCodigoAlDia:
    def test_pasa_y_no_imprime_traceback(self):
        r = _correr(RAIZ)
        assert "Traceback" not in r.stdout + r.stderr
        assert "VERIFICADO" in r.stdout, r.stdout[-1500:]
        assert r.returncode == 0


class TestConElPcDesactualizado:
    """Exactamente lo que le pasó a Yesid."""

    def test_no_muestra_un_traceback(self, tmp_path):
        r = _correr(_pc_desactualizado(tmp_path))
        assert "Traceback" not in r.stdout + r.stderr, r.stdout[-1500:]
        assert "ImportError" not in r.stdout

    def test_explica_en_castellano_que_paso(self, tmp_path):
        salida = _correr(_pc_desactualizado(tmp_path)).stdout
        assert "todavia no le" in salida and "codigo nuevo" in salida

    def test_dice_que_hacer(self, tmp_path):
        salida = _correr(_pc_desactualizado(tmp_path)).stdout
        assert "autodeploy_motor_local.cmd" in salida

    def test_no_dice_VERIFICADO_cuando_no_pudo_verificar(self, tmp_path):
        """Lo peor sería decir «todo bien» sin haber podido revisar."""
        r = _correr(_pc_desactualizado(tmp_path))
        assert "VERIFICADO - todo el trabajo" not in r.stdout
        assert "DESACTUALIZADO" in r.stdout
        assert r.returncode != 0

    def test_las_revisiones_que_si_se_pueden_hacer_se_hacen(self, tmp_path):
        """Una revisión rota no puede tumbar las otras."""
        salida = _correr(_pc_desactualizado(tmp_path)).stdout
        assert "1) Glosas ADRES muestra las cantidades" in salida
        assert "[OK]" in salida, "no se alcanzó a hacer ninguna revisión"


class TestElBotDeDobleClic:
    def test_el_cmd_conserva_los_finales_de_linea_de_windows(self):
        datos = (RAIZ / "tools" / "VERIFICAR_TRABAJO_HOY.cmd").read_bytes()
        assert b"\r\n" in datos
        assert datos.replace(b"\r\n", b"").count(b"\n") == 0, "hay saltos sueltos sin CR"

    def test_el_cmd_llama_al_guion_que_existe(self):
        texto = (RAIZ / "tools" / "VERIFICAR_TRABAJO_HOY.cmd").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "verificar_trabajo_hoy.py" in texto
        assert GUION.exists()
