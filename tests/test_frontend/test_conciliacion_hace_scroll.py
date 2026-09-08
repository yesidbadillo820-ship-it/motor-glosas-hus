"""La pantalla de Conciliación tiene que poder desplazarse (07-09-2026).

EL SÍNTOMA. «La pantalla sigue sin dejar que la baje o suba.» El panel de
Conciliación cortaba su contenido a la altura de la ventana y lo de abajo
quedaba **inalcanzable**: el botón de descargar el acta, el panel del Excel
de la mesa y el formulario de nueva conciliación existían pero no se podía
llegar a ellos.

LA CAUSA. `.concil-area` era el único contenedor de panel de toda la
aplicación sin `flex:1; overflow-y:auto`. Todos los demás lo tienen —
`.usuarios-area`, `.dash-area`, `.alert-area`, `.contratos-area`— porque
`.panel.active` es `overflow:hidden` y el que scrollea es el de adentro.

Venía roto de antes; se hizo evidente al agregar el cuadro «Armar el acta»,
que sumó 500 px arriba y empujó el resto fuera de la ventana.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

HTML = (Path(__file__).resolve().parents[2] / "static" / "index.html").read_text(encoding="utf-8")


def _regla(nombre: str) -> str:
    m = re.search(re.escape(nombre) + r"\{([^}]*)\}", HTML)
    return m.group(1) if m else ""


class TestLaConciliacionSePuedeRecorrer:
    def test_el_area_de_conciliacion_scrollea(self):
        regla = _regla(".concil-area")
        assert regla, "desapareció la regla .concil-area"
        assert "overflow-y:auto" in regla, (
            "sin overflow-y:auto lo que pase de la altura de la ventana queda "
            "inalcanzable: el botón de descargar el acta deja de existir para el auditor"
        )
        assert "flex:1" in regla, "sin flex:1 no ocupa el alto disponible y no hay qué scrollear"

    def test_el_panel_de_afuera_sigue_recortando_a_proposito(self):
        """`.panel` recorta y el de adentro scrollea: es el patrón de toda la
        aplicación. Si el panel scrolleara, se movería también el encabezado."""
        assert "overflow:hidden" in _regla(".panel")

    @pytest.mark.parametrize(
        "area", [".usuarios-area", ".dash-area", ".alert-area", ".contratos-area", ".concil-area"]
    )
    def test_todas_las_areas_de_panel_siguen_el_mismo_patron(self, area):
        """La de conciliación era la única que se salía del molde."""
        regla = _regla(area)
        assert "overflow-y:auto" in regla and "flex:1" in regla, f"{area} se salió del patrón"
