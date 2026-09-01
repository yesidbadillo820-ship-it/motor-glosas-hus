"""Cada pantalla pide la lista que le corresponde (21-08-2026).

Cinco pantallas del portal solo arman un desplegable de «¿a quién le paso
esto?»: importación masiva, asignar en lote, reasignar una glosa, reasignar
todo lo de un gestor y el buscador de Ctrl+K. Para llenarlo pedían la lista
COMPLETA de usuarios y filtraban en el navegador.

Ahora piden `/usuarios/asignables`, que ya viene filtrada del servidor. La
lista completa quedó solo para la pantalla de Usuarios, que es la única que de
verdad administra cuentas — y que exige rol de coordinación.

Esta prueba cuida que nadie vuelva a poner `/usuarios/` en una pantalla que
solo necesita un desplegable: sería reabrir la puerta sin darse cuenta.
"""

from __future__ import annotations

import re
from pathlib import Path

RUTA = Path(__file__).resolve().parents[2] / "static" / "index.html"


def _texto() -> str:
    return RUTA.read_text(encoding="utf-8", errors="replace")


def _funcion_de(linea: int) -> str:
    """El nombre de la función que contiene esa línea."""
    nombre = "?"
    patron = re.compile(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")
    for n, texto in enumerate(_texto().splitlines(), 1):
        if n > linea:
            break
        m = patron.match(texto)
        if m:
            nombre = m.group(1)
    return nombre


def _lineas_que_piden(ruta: str) -> list[int]:
    """Las líneas que piden esa dirección TAL CUAL.

    Dos cuidados. Se exige que después de la comilla venga una coma o un
    paréntesis: sin eso, `/usuarios/` también casaría con
    `'/usuarios/'+id+'/rol'`, que es otra ruta —cambiar el rol de una persona—.
    Y se descartan las llamadas con `method:`, porque un POST a esa misma
    dirección CREA un usuario: tampoco es pedir la lista.
    """
    marca = re.compile(r"fetch\('" + re.escape(ruta) + r"'\s*[,)]")
    return [
        n
        for n, t in enumerate(_texto().splitlines(), 1)
        # Sin `method:` es una consulta. Con `method:'POST'` sobre esa misma
        # dirección se CREA un usuario, que es otra cosa y ya exige permiso.
        if marca.search(t) and "method:" not in t
    ]


# La única pantalla que administra cuentas de verdad.
PANTALLA_DE_USUARIOS = "loadUsuarios"

# Las que solo arman un desplegable.
DESPLEGABLES = {
    "initImportacionMasiva",
    "bulkAsignarGestor",
    "reasignarGlosaUI",
    "reasignarDeGestor",
    "cargarDatosSpotlight",
}


class TestLaListaCompletaSoloDondeHaceFalta:
    def test_solo_la_pantalla_de_usuarios_la_pide(self):
        quienes = {_funcion_de(n) for n in _lineas_que_piden("/usuarios/")}
        assert quienes == {PANTALLA_DE_USUARIOS}, (
            f"Estas pantallas piden la lista COMPLETA de usuarios sin "
            f"necesitarla: {sorted(quienes - {PANTALLA_DE_USUARIOS})}. Con el "
            f"rol de auditor eso ahora da error 403 y la pantalla se queda "
            f"sin datos; y si se abriera la puerta para que funcione, se "
            f"volvería a repartir el listado de cuentas a todo el mundo."
        )

    def test_la_pantalla_de_usuarios_sigue_pidiendola(self):
        """Es la que administra: si le quitamos la lista, se queda vacía."""
        assert _lineas_que_piden("/usuarios/"), "la pantalla de Usuarios se quedó sin su lista"


class TestLosDesplegablesPidenLoSuyo:
    def test_las_cinco_pantallas_piden_los_asignables(self):
        quienes = {_funcion_de(n) for n in _lineas_que_piden("/usuarios/asignables")}
        assert quienes == DESPLEGABLES, (
            f"faltan o sobran pantallas: faltan {sorted(DESPLEGABLES - quienes)}, "
            f"sobran {sorted(quienes - DESPLEGABLES)}"
        )

    def test_son_exactamente_cinco_sitios(self):
        assert len(_lineas_que_piden("/usuarios/asignables")) == 5


class TestNoSeRompioLoQueYaFuncionaba:
    def test_las_demas_rutas_de_usuarios_siguen_igual(self):
        """Crear, borrar, cambiar rol y contraseña no se tocaron."""
        t = _texto()
        for trozo in ("/usuarios/'+id+'/rol", "/usuarios/'+id+'/password", "/usuarios/'+id"):
            assert trozo in t, f"se perdió la llamada {trozo}"

    def test_el_javascript_sigue_compilando(self):
        """Un cambio de texto mal hecho deja el portal entero en blanco."""
        import shutil
        import subprocess
        import tempfile

        node = shutil.which("node")
        if not node:  # pragma: no cover - depende de la máquina
            import pytest

            pytest.skip("no hay node en esta máquina")

        bloques = re.findall(r"<script[^>]*>(.*?)</script>", _texto(), re.S)
        assert bloques, "el portal se quedó sin JavaScript"
        for i, codigo in enumerate(bloques):
            if not codigo.strip():
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write(codigo)
                tmp = f.name
            r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
            assert r.returncode == 0, f"bloque {i} no compila:\n{r.stderr}"
