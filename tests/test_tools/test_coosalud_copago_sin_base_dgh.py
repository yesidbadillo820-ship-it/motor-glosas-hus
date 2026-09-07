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


def test_autorizacion_no_nombra_a_otro_pagador(coo):
    # El área entregó el texto nombrando a NUEVA EPS (venía de ese flujo).
    # Mandarle a COOSALUD una respuesta que nombra a otro pagador es regalarle
    # la glosa.
    texto = coo.OBS_POR_TIPO["AUTORIZACION"]

    assert "NUEVA EPS" not in texto
    assert "COOSALUD" in texto
    assert "DECRETO 4747 DE 2007" in texto


def test_el_texto_de_topes_queda_guardado_pero_no_se_aplica_solo(coo):
    # Decisión del área (07-09-2026): las glosas de cobertura salen con RE9901 y
    # el texto de COBERTURA. El RE9602 queda disponible para cuando el área diga
    # en qué lote usarlo, pero el bot no lo pone por su cuenta.
    assert coo.COD_RTA_TOPES == "RE9602"
    assert "EXCEDE TOPES AUTORIZADOS" in coo.OBS_TOPES_AUTORIZADOS
    assert coo.OBS_TOPES_AUTORIZADOS not in coo.OBS_POR_TIPO.values()


# ─── Cruce por el principio de la descripción ────────────────────────────────


def _cruces_con(descripciones: dict[str, str]) -> dict:
    """cruces minimos con solo el indice de descripciones de una factura."""
    import sys

    sys.path.insert(0, str(_TOOLS))
    try:
        import consolidar_coosalud as coo
    finally:
        sys.path.remove(str(_TOOLS))
    return {"desc_lista": {"538183": [(coo.norm_desc(d), c) for c, d in descripciones.items()]}}


def test_oxigeno_cruza_con_oxigeno_medicinal(coo):
    # COOSALUD glosa "OXIGENO" con el código 1O1044511000101; DGH lo tiene como
    # V03AN01 "OXIGENO MEDICINAL". Ni el código ni la descripción coinciden, y
    # DGH tumbaba el cargue entero con "la cuenta por cobrar no tiene asociado
    # el servicio".
    cruces = _cruces_con({"V03AN01": "OXIGENO MEDICINAL", "903603": "CALCIO AUTOMATIZADO"})

    assert coo.cruzar_por_principio_desc(cruces, "538183", "OXIGENO") == "V03AN01"


def test_si_hay_dos_candidatos_no_se_arriesga(coo):
    # "OXIGENO" también es el principio de "OXIGENO MEDICINAL", pero no de
    # "CANULA NASAL PARA OXIGENO". Si aun así quedan dos, se deja quieto: mejor
    # perder una objeción que objetarle a DGH un servicio que no es.
    cruces = _cruces_con({"V03AN01": "OXIGENO MEDICINAL", "V03AN02": "OXIGENO DOMICILIARIO"})

    assert coo.cruzar_por_principio_desc(cruces, "538183", "OXIGENO") is None


def test_una_descripcion_muy_corta_no_cruza(coo):
    # Con "GEL" o "SOL" el parecido no dice nada.
    cruces = _cruces_con({"X1": "GEL CONDUCTOR ULTRASONIDO"})

    assert coo.cruzar_por_principio_desc(cruces, "538183", "GEL") is None


def test_sin_indice_no_estalla(coo):
    # Bases viejas (sin el índice nuevo) tienen que seguir corriendo.
    assert coo.cruzar_por_principio_desc({}, "538183", "OXIGENO") is None
