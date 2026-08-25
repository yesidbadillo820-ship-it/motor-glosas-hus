"""Los once lectores de pesos dan todos el mismo resultado.

Once herramientas tenían su propia copia de la regla. Ahora todas cuelgan de
`tools/_dinero.py`, y esta prueba lo verifica de la única forma que sirve:
pasándoles los mismos valores y exigiendo la misma respuesta.

Si mañana alguien "arregla" una de ellas por su cuenta, esta prueba lo caza.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

# Formatos reales de los archivos de los pagadores y del ERP.
CASOS: list[tuple[str, float]] = [
    ("1.234.567", 1234567.0),
    ("$ 950.000", 950000.0),
    ("$114.900", 114900.0),
    ("50.000", 50000.0),
    ("2.500", 2500.0),
    ("1.365,50", 1365.50),
    ("1.234.567,89", 1234567.89),
    ("1234", 1234.0),
]


def _cruces_dgh():
    """Importa `suite_cartera_hus.nucleo.cruces_dgh` sin que lo tape la interfaz.

    Otra prueba de la suite mete `tools/suite_cartera_hus/` en la ruta de
    búsqueda. A partir de ahí, `import suite_cartera_hus` resuelve al módulo de
    la **interfaz gráfica** —que importa `tkinter`, ausente en el servidor de
    integración— en vez de al paquete. Aislada la prueba pasaba; en la suite
    completa reventaba.

    No basta con poner `tools/` primero: la carpeta no tiene `__init__.py`, así
    que es un paquete de espacio de nombres, y Python solo lo arma **si no
    encuentra un módulo normal con ese nombre en ninguna entrada de la ruta**.
    Mientras `tools/suite_cartera_hus/` siga en la ruta, el archivo de la
    interfaz gana siempre. Por eso se retira esa entrada mientras dura la
    importación.

    Al terminar se deja todo como estaba: esta prueba no puede romperle la
    resolución a las demás.
    """
    import importlib

    estorbo = str(_TOOLS / "suite_cartera_hus")
    previo_path = list(sys.path)
    previo_mods = {k: v for k, v in sys.modules.items() if k.startswith("suite_cartera_hus")}
    for k in previo_mods:
        del sys.modules[k]
    sys.path[:] = [p for p in sys.path if Path(p).resolve() != Path(estorbo).resolve()]
    sys.path.insert(0, str(_TOOLS))
    try:
        return importlib.import_module("suite_cartera_hus.nucleo.cruces_dgh")
    finally:
        sys.path[:] = previo_path
        for k in list(sys.modules):
            if k.startswith("suite_cartera_hus"):
                del sys.modules[k]
        sys.modules.update(previo_mods)


def _lectores():
    """(nombre, función) de cada herramienta ya convergida."""
    import asistente_conciliacion_dispensario as asis
    import completar_tramite_glosas_aceptadas as ctga
    import consolidar_coosalud as coo
    import convertir_tramite_masivo as ctm
    import explorador_radicacion as expl
    import generar_acta_conciliacion_dispensario as acta
    import hoja_maestra_conciliacion as hoja
    import organizar_objeciones_emssanar as ems
    import organizar_objeciones_savia as sav
    import organizar_objeciones_vco as vco

    cruces_dgh = _cruces_dgh()

    return [
        ("savia", sav._num),
        ("emssanar", ems._a_entero),
        ("vco", vco._numero),
        ("consolidar_coosalud", coo.a_numero),
        ("cruces_dgh", cruces_dgh.a_numero),
        ("glosas_aceptadas", ctga.a_numero),
        ("acta_conciliacion", acta.num),
        ("hoja_maestra", hoja._num),
        ("explorador_radicacion", expl._parse_valor),
        ("convertir_tramite_masivo", ctm._num),
        ("asistente_dispensario", asis._num),
    ]


@pytest.mark.parametrize("crudo,esperado", CASOS)
def test_todos_leen_lo_mismo(crudo, esperado):
    """Ninguna herramienta puede discrepar de las demás sobre cuánto vale algo."""
    discrepan = []
    for nombre, fn in _lectores():
        try:
            obtenido = float(fn(crudo))
        except Exception as e:  # una que reviente también es una discrepancia
            discrepan.append(f"{nombre}: {type(e).__name__}")
            continue
        # Las que devuelven pesos enteros truncan los centavos; es correcto.
        if abs(obtenido - esperado) > 1.0:
            discrepan.append(f"{nombre}: {obtenido:,.2f}")
    assert not discrepan, (
        f"Para {crudo!r} se esperaba {esperado:,.2f} y estas no coinciden: {', '.join(discrepan)}"
    )


def test_ninguna_multiplica_por_cien():
    """El bug de SAVIA: `1.365,50` no puede dar 136.550 en ningún lado."""
    for nombre, fn in _lectores():
        assert float(fn("1.365,50")) < 2000, f"{nombre} infló el valor"


def test_ninguna_lee_cero_ni_divide_por_mil():
    """Los bugs del trámite y del acta: un millón no puede dar 0 ni 1.234."""
    for nombre, fn in _lectores():
        obtenido = float(fn("1.234.567"))
        assert obtenido > 1_000_000, f"{nombre} leyó {obtenido:,.2f}"
