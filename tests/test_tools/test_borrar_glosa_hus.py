"""Los dos scripts de mantenimiento de la base, probados de verdad.

01-09-2026. El auditor tuvo razón en dos cosas: los comandos `python -c` con
comillas escapadas se rompen en PowerShell, y yo había asumido el nombre del
archivo de la base. Ninguno de los dos scripts asume nada: encuentran la base
recorriendo el disco y reconocen las tablas POR SUS COLUMNAS, no por su nombre.

`borrar_glosa_hus.py` toca datos de producción de forma irreversible, así que
se prueba lo que puede salir mal: que borre lo que debe, que NO borre lo que no
debe, que la copia de seguridad quede antes del DELETE, y que cancelar no toque
nada.
"""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path("tools/borrar_glosa_hus.py").resolve()
FACTURA = "HUS0000601892"


@pytest.fixture
def base(tmp_path: Path) -> Path:
    """Una base con nombre y carpeta que el script no puede adivinar."""
    (tmp_path / "data").mkdir()
    ruta = tmp_path / "data" / "loquesea.db"
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE historial (id INTEGER PRIMARY KEY, creado_en TEXT, eps TEXT,"
        " codigo_glosa TEXT, valor_objetado REAL, factura TEXT)"
    )
    con.execute(
        "CREATE TABLE dictamen_versiones (id INTEGER PRIMARY KEY, glosa_id INTEGER,"
        " dictamen_html TEXT)"
    )
    con.execute("CREATE TABLE otra_cosa (id INTEGER PRIMARY KEY, x TEXT)")
    con.executemany(
        "INSERT INTO historial VALUES (?,?,?,?,?,?)",
        [
            (147, "2026-08-31", "NUEVA EPS", "CL4506", 7310000.0, FACTURA),
            (146, "2026-08-30", "COOSALUD", "TA0301", 1254000.0, "HUS0000999999"),
        ],
    )
    con.executemany(
        "INSERT INTO dictamen_versiones VALUES (?,?,?)",
        [(1, 147, "v1"), (2, 147, "v2"), (3, 146, "de la otra glosa")],
    )
    con.commit()
    con.close()
    return ruta


def _correr(cwd: Path, *args: str, entrada: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        input=entrada,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _filas(ruta: Path) -> tuple[list, list]:
    con = sqlite3.connect(ruta)
    try:
        return (
            con.execute("SELECT id FROM historial ORDER BY id").fetchall(),
            con.execute("SELECT id FROM dictamen_versiones ORDER BY id").fetchall(),
        )
    finally:
        con.close()


class TestEncuentraLaBaseSinQueLeDiganDonde:
    def test_la_halla_con_un_nombre_inventado(self, tmp_path: Path, base: Path):
        r = _correr(tmp_path, FACTURA, "--si")
        assert "data/loquesea.db" in r.stdout or "data\\loquesea.db" in r.stdout, r.stdout

    def test_identifica_las_tablas_por_sus_columnas(self, tmp_path: Path, base: Path):
        r = _correr(tmp_path, FACTURA, "--si")
        assert "Tabla de glosas   : historial" in r.stdout
        assert "Tabla de versiones: dictamen_versiones" in r.stdout


class TestBorraLoQueDebeYSoloEso:
    def test_borra_la_glosa_y_sus_versiones(self, tmp_path: Path, base: Path):
        _correr(tmp_path, FACTURA, "--si")
        glosas, versiones = _filas(base)
        assert glosas == [(146,)], "borró de más o de menos"
        assert versiones == [(3,)], "se llevó versiones de otra glosa"

    def test_informa_el_numero_exacto_de_filas(self, tmp_path: Path, base: Path):
        r = _correr(tmp_path, FACTURA, "--si")
        assert "Borradas en dictamen_versiones: 2 fila(s)" in r.stdout
        assert "Borradas en historial: 1 fila(s)" in r.stdout

    def test_muestra_lo_que_va_a_borrar_antes_de_hacerlo(self, tmp_path: Path, base: Path):
        r = _correr(tmp_path, FACTURA, "--si")
        i_lista = r.stdout.index("ESTO ES LO QUE SE VA A BORRAR")
        i_borrado = r.stdout.index("Borradas en")
        assert i_lista < i_borrado
        assert "id=147" in r.stdout and "NUEVA EPS" in r.stdout


class TestLaCopiaDeSeguridad:
    def test_queda_antes_del_delete(self, tmp_path: Path, base: Path):
        r = _correr(tmp_path, FACTURA, "--si")
        copias = list((tmp_path / "data").glob("loquesea.db.backup_*"))
        assert len(copias) == 1, "no se hizo copia de seguridad"
        assert r.stdout.index("Copia de seguridad") < r.stdout.index("Borradas en")

    def test_la_copia_conserva_la_glosa_borrada(self, tmp_path: Path, base: Path):
        _correr(tmp_path, FACTURA, "--si")
        copia = next((tmp_path / "data").glob("loquesea.db.backup_*"))
        con = sqlite3.connect(copia)
        try:
            assert (
                con.execute(
                    "SELECT COUNT(*) FROM historial WHERE factura = ?", (FACTURA,)
                ).fetchone()[0]
                == 1
            ), "la copia no sirve para restaurar"
        finally:
            con.close()


class TestCuandoNoDebeTocarNada:
    def test_cancelar_no_borra(self, tmp_path: Path, base: Path):
        antes = _filas(base)
        r = _correr(tmp_path, FACTURA, entrada="no\n")
        assert "Cancelado. No se tocó nada." in r.stdout
        assert _filas(base) == antes

    def test_solo_la_palabra_BORRAR_sirve(self, tmp_path: Path, base: Path):
        r = _correr(tmp_path, FACTURA, entrada="borrar\n")
        assert "Cancelado" in r.stdout, "aceptó minúsculas"
        assert _filas(base)[0] == [(146,), (147,)]

    def test_factura_inexistente_avisa_y_no_borra(self, tmp_path: Path, base: Path):
        antes = _filas(base)
        r = _correr(tmp_path, "HUS_NO_EXISTE", "--si")
        assert "No hay nada que borrar" in r.stdout
        assert r.returncode == 1
        assert _filas(base) == antes

    def test_sin_ninguna_base_no_revienta(self, tmp_path: Path):
        r = _correr(tmp_path, FACTURA, "--si")
        assert r.returncode == 1
        assert "No se encontró" in r.stdout
        assert "Traceback" not in r.stderr
