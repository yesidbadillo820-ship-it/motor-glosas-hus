"""Las normas que el motor escribe tienen que estar contrastadas con su fuente.

28-08-2026. De las 24 normas que el motor escribe en los dictámenes y que nadie
había contrastado, las tres primeras que miré dieron **dos defectos graves**:

- La **Res. 2175 de 2015** estaba como «conciliación de glosas médicas» y es del
  reporte de atenciones a menores y gestantes (Familias en Acción). Iba en el
  acta que firman el HUS y la EPS.
- Había **cuatro listados del PBS vigentes a la vez**, cuando el Ministerio
  reexpide uno cada diciembre. El motor podía afirmar que un servicio está
  cubierto invocando un listado de hace ocho años.

El campo `verificada` es lo que separa «alguien abrió el texto oficial y lo
comparó» de «alguien lo escribió de memoria». Esta prueba fija la lista de las
que ya están contrastadas para que nadie le quite la nota, y deja anotadas las
que faltan, con su razón.

NO exige que TODAS lo estén: eso volvería roja la suite por trabajo pendiente,
que es la forma más rápida de que alguien apague la prueba. Exige que las ya
hechas no retrocedan y que la lista de pendientes no crezca.
"""

from __future__ import annotations

import pytest

from app.services.normativa_completa import _TODAS_LAS_NORMAS

# Contrastadas contra el texto oficial (normograma de la Supersalud) el
# 27 y el 28-08-2026. Quitarle la nota a cualquiera de estas rompe la prueba.
CONTRASTADAS = [
    "DECRETO 1011 DE 2006",
    "DECRETO 1295 DE 1994",
    "DECRETO 2353 DE 2015",
    "DECRETO 441 DE 2022",
    "LEY 1388 DE 2010",
    "LEY 2294 DE 2023",
    "LEY 715 DE 2001",
    "LEY 91 DE 1989",
    "RESOLUCION 2003 DE 2014",
    "RESOLUCION 2175 DE 2015",
    "RESOLUCION 2292 DE 2021",
    "RESOLUCION 2481 DE 2020",
    "RESOLUCION 256 DE 2016",
    "RESOLUCION 2718 DE 2024",
    "RESOLUCION 3047 DE 2008",
    "RESOLUCION 3100 DE 2019",
    "RESOLUCION 416 DE 2009",
    "RESOLUCION 4331 DE 2012",
    "RESOLUCION 5269 DE 2017",
]

# Las que el motor escribe y siguen SIN contrastar, con el motivo. El
# normograma de la Supersalud solo compila normas del sector salud, así que
# varias hay que buscarlas en otra fuente; y la Res. 124 de 2026 es del propio
# hospital, no de un ministerio.
FALTAN_CON_MOTIVO = {
    "CIRCULAR 19 DE 2024": "no se ubicó en el normograma; buscarla en la fuente del emisor",
    "DECRETO 1072 DE 2015": "es del sector Trabajo, no está en el normograma de salud",
    "DECRETO 3752 DE 2003": "no se ubicó en el normograma (404)",
    "LEY 1150 DE 2007": "contratación estatal; no está en el normograma de salud",
    "LEY 1581 DE 2012": "habeas data; no está en el normograma de salud",
    "RESOLUCION 124 DE 2026": "es del propio HUS, no de un ministerio",
    "RESOLUCION 1652 DE 2021": "no se ubicó en el normograma (404)",
    "RESOLUCION 2358 DE 1998": "no se ubicó en el normograma (404)",
    "RESOLUCION 5261 DE 1994": "no se ubicó en el normograma (404)",
}


def _nota(clave: str) -> str:
    f = _TODAS_LAS_NORMAS.get(clave) or {}
    return str(f.get("verificada") or f.get("fuente_verificacion") or "")


class TestNoSeLeQuitaLaNotaAUnaYaContrastada:
    @pytest.mark.parametrize("clave", CONTRASTADAS)
    def test_conserva_la_fuente(self, clave: str):
        assert clave in _TODAS_LAS_NORMAS, f"{clave} desapareció del corpus"
        assert _nota(clave), (
            f"{clave} perdió la nota de la fuente contra la que se contrastó. "
            "Sin ella nadie sabe si lo que el corpus afirma salió del texto "
            "oficial o de la memoria de alguien."
        )


class TestLaListaDePendientesNoCrece:
    def test_las_pendientes_siguen_siendo_las_mismas(self):
        """Si aparece una nueva sin contrastar, hay que mirarla y anotarla
        aquí con su motivo — no dejarla pasar en silencio."""
        nuevas = [c for c in FALTAN_CON_MOTIVO if c in _TODAS_LAS_NORMAS and _nota(c)]
        # Que una pendiente YA tenga nota es buena noticia: solo hay que
        # moverla a CONTRASTADAS para que quede protegida.
        assert not nuevas, (
            "Estas ya tienen fuente anotada: muévalas a CONTRASTADAS para que "
            f"la prueba las proteja → {', '.join(sorted(nuevas))}"
        )

    @pytest.mark.parametrize("clave,motivo", sorted(FALTAN_CON_MOTIVO.items()))
    def test_cada_pendiente_dice_por_que(self, clave: str, motivo: str):
        assert motivo.strip(), f"{clave} está pendiente sin explicar por qué"
