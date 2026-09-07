"""El tope por COPAGO debe aplicarse aunque NO se haya pasado la base de DGH.

Lección del lote del 07-09-2026: se armaron los OBJECIONES sin el export de
servicios de DGH y las facturas con cuota moderadora salieron objetando el
valor completo del servicio. DGH las rechaza con "El VALOR OBJECION no puede
ser mayor al valor del servicio", y como el cargue es todo o nada, tumba el
archivo entero.

El dato que hace falta para capar NO viene de DGH: el valor del servicio y el
copago vienen del propio DETALLE de COOSALUD. Así que el guardián de valor
tiene que correr siempre, con base DGH o sin ella.
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[2] / "tools"


@pytest.fixture(scope="module")
def coo():
    sys.path.insert(0, str(_TOOLS))
    try:
        yield importlib.import_module("consolidar_coosalud")
    finally:
        sys.path.remove(str(_TOOLS))


def _servicio(codigo: str, valor_servicio: float, copago: float, glosado: float) -> dict:
    return {
        "factura": "HUS0000538766",
        "id_detalle": f"det-{codigo}-{int(glosado)}",
        "codigo_servicio": codigo,
        "descripcion": "SERVICIO DE PRUEBA",
        "valor_glosado": glosado,
        "valor_servicio": valor_servicio,
        "copago": copago,
        "observacion": "TA2901 MAYOR VALOR COBRADO",
        "conceptos": ["TA2901"],
        "codigo_mayor": "TA2901",
    }


def _valores(filas: list[list]) -> list[float]:
    """CROVALOBJ de cada fila del OBJECIONES (columna 14, índice 13)."""
    return [float(f[13]) for f in filas]


def test_sin_base_dgh_el_copago_se_capa(coo):
    # El caso real de HUS536627: se glosa el valor completo y el copago es el 10%.
    glosados = [_servicio("903883", 4700, 470, 4700)]

    filas, _no_cruzados, ajustados = coo.generar_objeciones(
        glosados, datetime(2026, 9, 7), cruces=None
    )

    assert _valores(filas) == [4230], "debía caparse a valor del servicio - copago"
    assert len(ajustados) == 1, "el ajuste tiene que quedar reportado"


def test_sin_base_dgh_el_tope_es_la_suma_de_las_lineas_del_servicio(coo):
    # Lección de las 8 estancias: la capacidad de un servicio es la SUMA de sus
    # líneas en la factura, no la de una sola. Tres líneas de $1.000 admiten
    # objetar $3.000 en total, no $1.000.
    glosados = [_servicio("129A02", 1000, 0, 1000) for _ in range(3)]
    for i, s in enumerate(glosados):
        s["id_detalle"] = f"det-{i}"

    filas, _no_cruzados, ajustados = coo.generar_objeciones(
        glosados, datetime(2026, 9, 7), cruces=None
    )

    assert sum(_valores(filas)) == 3000
    assert ajustados == [], "nada se pasa del tope: no debía capar"


def test_sin_base_dgh_la_glosa_total_se_capa_al_valor_del_servicio(coo):
    # HUS538766: COOSALUD glosó $20.869.844 contra una estancia de $5.260.800.
    # DGH no acepta más que el valor del servicio (menos el copago).
    glosados = [_servicio("130A02", 5_260_800, 5_000, 20_869_844)]

    filas, _no_cruzados, ajustados = coo.generar_objeciones(
        glosados, datetime(2026, 9, 7), cruces=None
    )

    assert _valores(filas) == [5_255_800]
    assert len(ajustados) == 1


def test_sin_valor_de_servicio_no_se_capa(coo):
    # Si el DETALLE no trae el valor, mejor no topar que topar con un dato
    # incompleto: la objeción sale como la mandó la EPS.
    s = _servicio("890701", 0, 0, 97_671)
    s["valor_servicio"] = None
    s["copago"] = None

    filas, _no_cruzados, ajustados = coo.generar_objeciones([s], datetime(2026, 9, 7), cruces=None)

    assert _valores(filas) == [97_671]
    assert ajustados == []


# ─── Textos de respuesta actualizados por el área el 07-09-2026 ───────────────


def test_la_extemporanea_lleva_los_dias_y_la_fecha_de_la_factura(coo):
    # Antes iba un texto genérico y al auditor le tocaba completar a mano los
    # días hábiles y la fecha en cada factura.
    from datetime import date

    texto = coo.obs_extemporanea(25, date(2026, 7, 31))

    assert "HAN TRANSCURRIDO 25 DÍAS HÁBILES" in texto
    assert "(2026-07-31)" in texto
    assert "DECRETO 441 DE 2022" in texto, "la nota de aceptación tácita debe ir"
    assert "xx" not in texto and "XXXX-XX-XX" not in texto


def test_sin_datos_la_extemporanea_deja_los_huecos_a_la_vista(coo):
    # Si no hay días ni fecha, el hueco se ve: nadie debe dar por buena una
    # respuesta a medio llenar.
    texto = coo.obs_extemporanea()

    assert "HAN TRANSCURRIDO xx DÍAS HÁBILES" in texto
    assert "(XXXX-XX-XX)" in texto


def test_cobertura_la_responde_cartera_y_tiene_texto(coo):
    # Las doctoras solo contestan CALIDAD. Cobertura tiene su propio texto, así
    # que no puede quedar sin responder ni sacar la factura del cargue.
    assert coo.TIPO_POR_PREFIJO["CO"] == "COBERTURA"
    texto = coo.OBS_POR_TIPO["COBERTURA"]

    assert texto, "COBERTURA debe tener texto del área"
    assert "68001S00060339-24" in texto and "68001C00060340-24" in texto
    assert "DECRETO 441 DE 2022" in texto
    assert "CALIDAD" not in coo.OBS_POR_TIPO, "CALIDAD sí la responden las doctoras"
