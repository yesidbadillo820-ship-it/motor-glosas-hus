"""Pruebas del bot que carga las respuestas en SIIFA.

Lo que se cuida acá es lo más delicado de todo el flujo: que cada respuesta
entre por la puerta que le corresponde. Una DEVOLUCIÓN se responde en otro
endpoint y con otra lista de códigos que una glosa; el identificador, en
cambio, es el mismo (idSeguimientoFactura). Meter una devolución por la
puerta de las glosas es lo que hacía que SIIFA rechazara el código RE9701
diciendo que «no pertenece al grupo RESPUESTA».
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from openpyxl import Workbook

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import responder_glosas_siifa as bot  # noqa: E402

COLS = [
    "ID_SEGUIMIENTO_FACTURA_GLOSA",
    "ID_SEGUIMIENTO_FACTURA_DEVOLUCION",
    "NUMERO_FACTURA",
    "TIPO",
    "CODIGO_RESPUESTA",
    "FECHA_RESPUESTA",
    "OBSERVACION_RESPUESTA",
]


class ClienteFalso:
    """Anota por dónde y con qué id se mandó cada respuesta."""

    def __init__(self):
        self.glosas: list[tuple] = []
        self.devoluciones: list[tuple] = []
        self.reiteraciones: list[tuple] = []

    def responder_glosa(self, ident, codigo, observacion=None, fecha=None):
        self.glosas.append((ident, codigo, observacion, fecha))
        return {}

    def responder_devolucion(self, ident, codigo, observacion=None, fecha=None):
        self.devoluciones.append((ident, codigo, observacion, fecha))
        return {}

    def responder_reiteracion_glosa(self, ident, codigo, observacion=None, fecha=None):
        self.reiteraciones.append((ident, codigo, observacion, fecha))
        return {}


def _excel(tmp_path: Path, filas: list[dict], cols=COLS) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "RESPUESTAS"
    ws.append(cols)
    for f in filas:
        ws.append([f.get(c) for c in cols])
    ruta = tmp_path / "respuestas.xlsx"
    wb.save(ruta)
    return ruta


def _fila(ident, tipo="GLOSA", id_dev=None, codigo="RE9901"):
    return {
        "ID_SEGUIMIENTO_FACTURA_GLOSA": ident,
        "ID_SEGUIMIENTO_FACTURA_DEVOLUCION": id_dev,
        "NUMERO_FACTURA": "HUS454747",
        "TIPO": tipo,
        "CODIGO_RESPUESTA": codigo,
        "FECHA_RESPUESTA": "2026-05-11",
        "OBSERVACION_RESPUESTA": "ESE HUS NO ACEPTA.",
    }


def _procesar(tmp_path: Path, excel: Path, cliente, accion="respuesta") -> list[dict]:
    filas = bot.leer_excel(excel, None)
    reporte = tmp_path / "reporte.csv"
    with open(reporte, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id_seguimiento_factura_glosa",
                "numero_factura",
                "estado",
                "detalle",
                "fecha_hora",
            ],
        )
        writer.writeheader()
        bot.procesar(cliente, filas, accion, set(), writer)
    with open(reporte, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_una_glosa_va_por_la_puerta_de_las_glosas(tmp_path):
    cliente = ClienteFalso()
    excel = _excel(tmp_path, [_fila(15110544)])

    _procesar(tmp_path, excel, cliente)

    assert cliente.glosas == [(15110544, "RE9901", "ESE HUS NO ACEPTA.", "2026-05-11T12:00:00Z")]
    assert cliente.devoluciones == []


def test_una_devolucion_va_por_su_puerta(tmp_path):
    """Si el archivo trae un id de devolución explícito, ese manda."""
    cliente = ClienteFalso()
    excel = _excel(tmp_path, [_fila(15110544, tipo="DEVOLUCION", id_dev=7788, codigo="RE9701")])

    _procesar(tmp_path, excel, cliente)

    assert cliente.devoluciones == [(7788, "RE9701", "ESE HUS NO ACEPTA.", "2026-05-11T12:00:00Z")]
    assert cliente.glosas == [], "una devolución nunca puede irse por la puerta de las glosas"


def test_una_devolucion_usa_el_id_del_seguimiento(tmp_path):
    """No hay dos ids: hay uno solo.

    El volcado crudo de la API (factura HUS494196, 05-08-2026) mostró que un
    seguimiento de tipo DEVOLUCION trae idSeguimientoFactura y nada más. Lo
    que cambia entre glosa y devolución es la puerta y la lista de códigos,
    no el identificador. Por eso los archivos ya generados sirven tal cual.
    """
    cliente = ClienteFalso()
    excel = _excel(tmp_path, [_fila(17888681, tipo="DEVOLUCION", id_dev=None, codigo="RE9701")])

    _procesar(tmp_path, excel, cliente)

    assert cliente.devoluciones == [
        (17888681, "RE9701", "ESE HUS NO ACEPTA.", "2026-05-11T12:00:00Z")
    ]
    assert cliente.glosas == [], "una devolución nunca puede irse por la puerta de las glosas"


def test_sin_columna_tipo_todo_sigue_yendo_como_glosa(tmp_path):
    """Compatibilidad: los archivos viejos no traen la columna TIPO."""
    cliente = ClienteFalso()
    cols = [c for c in COLS if c not in ("TIPO", "ID_SEGUIMIENTO_FACTURA_DEVOLUCION")]
    excel = _excel(tmp_path, [_fila(15110544)], cols=cols)

    _procesar(tmp_path, excel, cliente)

    assert len(cliente.glosas) == 1
    assert cliente.devoluciones == []


def test_la_subsanacion_sigue_yendo_por_su_endpoint(tmp_path):
    cliente = ClienteFalso()
    excel = _excel(tmp_path, [_fila(15110544)])

    _procesar(tmp_path, excel, cliente, accion="reiteracion-respuesta")

    assert len(cliente.reiteraciones) == 1
    assert cliente.glosas == []
    assert cliente.devoluciones == []


def test_el_reporte_deja_la_devolucion_identificada(tmp_path):
    """Para poder reintentar hay que saber de qué fila se trata."""
    cliente = ClienteFalso()
    excel = _excel(tmp_path, [_fila(15110544, tipo="DEVOLUCION", id_dev=7788, codigo="RE9701")])

    reporte = _procesar(tmp_path, excel, cliente)

    assert reporte[0]["estado"] == "OK"
    assert reporte[0]["id_seguimiento_factura_glosa"] == "15110544"
    assert reporte[0]["numero_factura"] == "HUS454747"
