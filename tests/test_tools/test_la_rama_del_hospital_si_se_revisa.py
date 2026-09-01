"""La rama que llega al hospital tiene que pasar por el CI (21-08-2026).

EL DESCUBRIMIENTO. El PC de cartera baja el código cada 5 minutos de la rama
`motor-glosas` (lo hace `tools/autodeploy_motor_local.cmd`). Esa es, por
lejos, la rama más delicada del repositorio: es la única que de verdad llega
al hospital.

Y era la única que **no** se revisaba. El CI corría en las ramas de trabajo
(`claude/**`) y en `main`/`develop`, pero no en `motor-glosas`. O sea: todo se
comprobaba **antes** de fusionar y nada **después**. Una fusión mal resuelta
—dos trabajos en paralelo tocando el mismo archivo, que aquí pasa seguido—
llegaba al hospital sin que nada la mirara.

Se notó el 21-08 por la tarde: el portal se cayó tras un reinicio, la
corrección se fusionó, y el resultado fusionado no tuvo ni un CI terminado.

Estas pruebas cuidan que la rama del hospital siga en la lista. Es una línea
fácil de borrar sin darse cuenta de lo que cuesta.
"""

from __future__ import annotations

import re
from pathlib import Path

RUTA = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"

# La rama de la que el PC de cartera baja el código. Si esto cambia, tiene que
# cambiar también en tools/autodeploy_motor_local.cmd.
RAMA_DEL_HOSPITAL = "motor-glosas"
AUTODEPLOY = Path(__file__).resolve().parents[2] / "tools" / "autodeploy_motor_local.cmd"


def _ramas_de(disparador: str) -> list[str]:
    """Las ramas que disparan el CI para `push` o para `pull_request`.

    Se lee con una expresión regular a propósito, y no con PyYAML: esa librería
    no es dependencia declarada del proyecto, y una prueba no puede exigir
    instalar algo nuevo solo para leer dos renglones.
    """
    texto = RUTA.read_text(encoding="utf-8")
    m = re.search(rf"^  {disparador}:\n(?:.*\n)*?\s*branches:\s*\[(.*?)\]", texto, re.M)
    assert m, f"no se encontró la lista de ramas de `{disparador}` en ci.yml"
    return [x.strip().strip("\"'") for x in m.group(1).split(",")]


class TestLaRamaDelHospitalSeRevisa:
    def test_el_ci_corre_al_subir_a_esa_rama(self):
        ramas = _ramas_de("push")
        assert RAMA_DEL_HOSPITAL in ramas, (
            f"'{RAMA_DEL_HOSPITAL}' no está en los disparadores del CI. Es la "
            f"rama de la que el PC de cartera baja el código cada 5 minutos: "
            f"sin CI, una fusión mal resuelta llega al hospital sin que nada "
            f"la mire."
        )

    def test_y_tambien_en_los_PR_que_apuntan_a_ella(self):
        ramas = _ramas_de("pull_request")
        assert RAMA_DEL_HOSPITAL in ramas, (
            "Los PR que apuntan a la rama del hospital no disparan el CI: se "
            "fusionaría sin haber comprobado nada."
        )

    def test_es_de_verdad_la_rama_de_la_que_baja_el_PC(self):
        """Si el autodespliegue cambiara de rama, esta prueba quedaría
        cuidando la rama equivocada y nadie se enteraría."""
        t = AUTODEPLOY.read_bytes().decode("utf-8", errors="replace")
        assert f"origin/{RAMA_DEL_HOSPITAL}" in t, (
            f"El autodespliegue ya no baja de '{RAMA_DEL_HOSPITAL}'. Hay que "
            f"actualizar esta prueba Y los disparadores del CI, o la rama que "
            f"llega al hospital se queda otra vez sin revisar."
        )


class TestNoSeAflojoLoQueYaSeRevisaba:
    def test_las_ramas_de_trabajo_siguen_revisandose(self):
        ramas = _ramas_de("push")
        assert "claude/**" in ramas

    def test_el_ci_sigue_haciendo_las_tres_cosas(self):
        """Formato, reglas de alta señal y pruebas. Si alguna se cae de la
        lista, el CI pasa en verde sin haber comprobado lo que importa."""
        t = RUTA.read_text(encoding="utf-8")
        assert "ruff check . --select F,W6" in t
        assert "ruff format --check ." in t
        assert "pytest" in t
