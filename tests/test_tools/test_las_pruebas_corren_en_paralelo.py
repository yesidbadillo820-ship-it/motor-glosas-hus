"""El CI no puede volver a tardar quince minutos.

10-09-2026, con las palabras de Yesid: «tengo que esperar hasta 15 minutos
que un PR pase una validación y aparte de eso todos salen con conflictos».

Eran 13 minutos reales, y con cada conflicto había que volver a esperarlos.
La suite ahora se reparte entre los núcleos del runner:

    en serie ............................. 13 min
    -n 4 (reparto por prueba) ............ MÁS LENTO — las pruebas se pisan
    -n 4 --dist loadfile ................. 3 min 38 s · 12.587 en verde

`--dist loadfile` no es un adorno: reparte por ARCHIVO, así que todas las
pruebas de un mismo archivo caen en el mismo proceso. Sin eso, dos pruebas
que comparten la base de prueba o un archivo temporal se pisan, y la suite
empieza a fallar por razones que no tienen que ver con el código. Cambiar
quince minutos de espera por un verde poco fiable sería peor que no hacer
nada — por eso esta prueba vigila las DOS banderas, no solo la de velocidad.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CI = RAIZ / ".github" / "workflows" / "ci.yml"


def _ci() -> str:
    return CI.read_text(encoding="utf-8")


class TestLaSuiteSeReparte:
    def test_el_ci_corre_en_paralelo(self):
        assert "-n auto" in _ci(), "sin esto la suite vuelve a tardar 13 minutos"

    def test_reparte_por_archivo_y_no_por_prueba(self):
        """La bandera que evita que las pruebas se pisen entre sí."""
        assert "--dist loadfile" in _ci(), (
            "sin --dist loadfile, dos pruebas que comparten la base de prueba "
            "caen en procesos distintos y se pisan: verde poco fiable"
        )

    def test_las_dos_banderas_van_juntas(self):
        """Una sin la otra es peor que ninguna."""
        t = _ci()
        assert ("-n auto" in t) == ("--dist loadfile" in t)


class TestLaHerramientaEstaDeclarada:
    def test_el_ci_la_instala(self):
        assert "pytest-xdist" in _ci()

    def test_tambien_esta_en_requirements_dev(self):
        """Para que en el PC del que trabaja corra igual que en el CI."""
        req = (RAIZ / "requirements-dev.txt").read_text(encoding="utf-8")
        assert "pytest-xdist" in req

    def test_va_con_version_fija(self):
        """Igual que ruff: una versión suelta rompe el gate de todas las ramas."""
        req = (RAIZ / "requirements-dev.txt").read_text(encoding="utf-8")
        linea = next(ln for ln in req.split("\n") if ln.startswith("pytest-xdist"))
        assert "==" in linea, f"pytest-xdist sin versión fija: {linea}"
