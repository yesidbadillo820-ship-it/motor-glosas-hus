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


# ─── La busqueda de los soportes de una factura ──────────────────────────────


class TestBuscarLosSoportesDeUnaFactura:
    """19-08-2026. Yesid corrió el verificador con HUS468334 y la pantalla se
    quedó en «Buscando los soportes... en el servidor».

    La causa: se llamaba a `get_indexer().lookup()`, que en un proceso aparte
    encuentra el índice frío y se pone a indexar el servidor ENTERO — 11.367
    facturas y 102.729 archivos por red. Minutos sin imprimir nada, y todo ese
    trabajo se botaba al cerrar el programa. Y el encabezado decía «esto solo
    mira, no cuesta».

    Ahora se busca solo esa factura y se para al encontrar su carpeta.
    """

    def _servidor(self, tmp_path: Path, ruido: int = 40) -> Path:
        base = (
            tmp_path
            / "2. FEBRERO 2026 - SOPORTES RADICACION CARPETA 2"
            / "ALIANZA MEDELLIN"
            / "SOFIA"
            / "ENV-232984-okdgh"
            / "SOPORTES"
        )
        for n in range(ruido):
            d = base / f"HUS4{n:05d}"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"FEV_900006037_HUS4{n:05d}.pdf").write_bytes(b"%PDF-1.4\n" + b"0" * 2048)
        d = base / "HUS468334"
        d.mkdir(parents=True, exist_ok=True)
        for n in (
            "FEV_900006037_HUS468334.pdf",
            "HEV_900006037_HUS468334.pdf",
            "EPICRISIS HUS468334.pdf",
            "HOJA DE ADMINISTRACION DE MEDICAMENTOS HUS468334.pdf",
        ):
            (d / n).write_bytes(b"%PDF-1.4\n" + b"0" * 2048)
        (d / "RIPS_900006037_HUS468334.json").write_bytes(b"{}" + b"0" * 2000)
        return tmp_path

    def _buscar(self, monkeypatch, raiz: Path, factura: str):
        import sys

        sys.path.insert(0, str(RAIZ / "tools"))
        import verificar_trabajo_hoy as v
        from app.services import soportes_autodiscovery_service as svc

        class _Idx:
            def __init__(self):
                self.raiz = raiz

        monkeypatch.setattr(svc, "get_indexer", lambda: _Idx())
        return v.buscar_soportes_de_una_factura(factura)

    def test_encuentra_los_soportes_de_la_factura(self, monkeypatch, tmp_path):
        sop = self._buscar(monkeypatch, self._servidor(tmp_path), "HUS468334")
        nombres = {s["nombre_archivo"] for s in sop}
        assert "HEV_900006037_HUS468334.pdf" in nombres
        assert "HOJA DE ADMINISTRACION DE MEDICAMENTOS HUS468334.pdf" in nombres

    def test_no_se_trae_los_soportes_de_otras_facturas(self, monkeypatch, tmp_path):
        sop = self._buscar(monkeypatch, self._servidor(tmp_path), "HUS468334")
        assert all("468334" in s["nombre_archivo"] for s in sop), [s["nombre_archivo"] for s in sop]

    def test_clasifica_con_las_reglas_del_indexador(self, monkeypatch, tmp_path):
        """No puede haber dos verdades sobre qué es una historia clínica."""
        sop = self._buscar(monkeypatch, self._servidor(tmp_path), "HUS468334")
        tipos = {s["nombre_archivo"]: s["tipo"] for s in sop}
        assert tipos["HEV_900006037_HUS468334.pdf"] == "historia_clinica"
        assert tipos["RIPS_900006037_HUS468334.json"] == "rips"

    def test_es_rapido_aunque_haya_ruido_alrededor(self, monkeypatch, tmp_path):
        import time

        raiz = self._servidor(tmp_path, ruido=300)
        arranque = time.time()
        sop = self._buscar(monkeypatch, raiz, "HUS468334")
        assert sop
        assert time.time() - arranque < 10, "se está recorriendo el servidor entero"

    def test_sin_servidor_avisa_en_vez_de_reventar(self, monkeypatch, tmp_path):
        assert self._buscar(monkeypatch, tmp_path / "no_existe", "HUS468334") is None

    def test_un_numero_que_no_es_factura_avisa(self, monkeypatch, tmp_path):
        assert self._buscar(monkeypatch, self._servidor(tmp_path), "no-es-factura") is None

    def test_factura_que_no_esta_devuelve_lista_vacia(self, monkeypatch, tmp_path):
        assert self._buscar(monkeypatch, self._servidor(tmp_path), "HUS999999") == []

    def test_ya_no_dispara_el_indexado_completo(self):
        """La regresión concreta: `lookup()` reconstruye el índice entero.

        Se mira el CÓDIGO, no los comentarios — este archivo explica la falla
        y nombrarla no puede hacer fallar la prueba.
        """
        import ast

        arbol = ast.parse((RAIZ / "tools" / "verificar_trabajo_hoy.py").read_text(encoding="utf-8"))
        llamadas = [
            n.func.attr
            for n in ast.walk(arbol)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        ]
        assert "lookup" not in llamadas, (
            "el verificador volvió a indexar el servidor entero para mirar una factura"
        )
