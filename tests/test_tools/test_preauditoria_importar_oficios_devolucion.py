"""Pruebas del importador de oficios de devolución históricos (DEV-PRE-AUD)."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import openpyxl
import pytest

RAIZ = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location(
    "preauditoria_importar_oficios_devolucion",
    RAIZ / "tools" / "preauditoria_importar_oficios_devolucion.py",
)
imp = importlib.util.module_from_spec(spec)
sys.modules["preauditoria_importar_oficios_devolucion"] = imp
spec.loader.exec_module(imp)


@pytest.fixture()
def db(tmp_path):
    from sqlalchemy import create_engine
    from app.models.db import Base

    ruta = tmp_path / "motorglosas.db"
    engine = create_engine(f"sqlite:///{ruta}")
    Base.metadata.create_all(engine)
    engine.dispose()
    con = sqlite3.connect(ruta)
    # Una factura devuelta con su evento (como las deja el importador del
    # consolidado) y otra sin evento de devolución.
    con.execute(
        "INSERT INTO preaud_facturas (id, factura, estado, resultado_actual, "
        "ronda_actual, num_subsanacion, num_devoluciones, pendiente_subsanacion) "
        "VALUES (1, 'HUS0000541371', 'DEVUELTA_PEND_SUBSANACION', 'DEVUELTA', 1, 0, 1, 1)"
    )
    con.execute(
        "INSERT INTO preaud_factura_eventos (factura_id, factura, tipo_evento, "
        "subsanacion_num, ronda, envio, oficio_fhus, motivo, valor_snapshot) "
        "VALUES (1, 'HUS0000541371', 'DEVUELTA', 0, 1, '232018', "
        "'FHUS-AS-I01098-26', 'NO SE ENCUENTRAN SOPORTES', 1497600)"
    )
    con.execute(
        "INSERT INTO preaud_facturas (id, factura, estado, resultado_actual, "
        "ronda_actual, num_subsanacion, num_devoluciones, pendiente_subsanacion) "
        "VALUES (2, 'HUS0000999999', 'RADICADA', 'RADICAR', 1, 0, 0, 0)"
    )
    con.execute(
        "INSERT INTO preaud_oficios_recepcion (id, numero_radicado, fecha_recibido) "
        "VALUES (50, 'FHUS-AS-I01098-26', '2026-07-30 08:00:00')"
    )
    con.commit()
    con.close()
    return str(ruta)


def _excel(tmp_path, bloques):
    """bloques: [(consecutivo, fecha_texto, [(envio, factura, valor, oficio, motivo)])]"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PREAUDITORIA"
    for consec, fecha, filas in bloques:
        ws.append(
            [
                None,
                "ENTREGA DE DEVOLUCIONES",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                f"Consecutivo: {consec}",
            ]
        )
        ws.append(
            [
                None,
                "FACTURAS",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                f"Fecha:                       {fecha}",
            ]
        )
        ws.append(
            [
                None,
                "No.",
                "ENVIO",
                "FACTURA",
                "F_FACTURA",
                "VALOR",
                "NIT",
                "ENTIDAD",
                "OFICIO",
                "MOTIVO",
            ]
        )
        for i, (envio, factura, valor, oficio, motivo) in enumerate(filas, 1):
            ws.append(
                [
                    None,
                    i,
                    envio,
                    factura,
                    "24/07/2026",
                    valor,
                    "860002184",
                    "AXA COLPATRIA SEGUROS S.A.",
                    oficio,
                    motivo,
                ]
            )
    ruta = tmp_path / "oficios_dev.xlsx"
    wb.save(ruta)
    return str(ruta)


def _correr(ruta_excel, ruta_db, aplicar=False, desde="30/07/2026"):
    argv = ["prog", ruta_excel, "--desde", desde] + (["aplicar"] if aplicar else []) + [ruta_db]
    viejo = sys.argv
    sys.argv = argv
    try:
        assert imp.main() == 0
    finally:
        sys.argv = viejo


BLOQUE_0104 = (
    "DEV-PRE-AUD-0104-2026",
    "4/08/2026",
    [("232018", "HUS0000541371", "1.497.600", "FHUS-AS-I01098-26", "NO SE ENCUENTRAN SOPORTES")],
)


def test_crea_oficio_y_amarra_evento(db, tmp_path):
    xlsx = _excel(tmp_path, [BLOQUE_0104])
    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    consec, anio, numero, rec_id, total_f, total_v = con.execute(
        "SELECT consecutivo, anio, numero, oficio_recepcion_id, total_facturas, total_valor "
        "FROM preaud_oficios_devolucion"
    ).fetchone()
    assert (consec, anio, numero, rec_id, total_f) == ("DEV-PRE-AUD-0104-2026", 2026, 104, 50, 1)
    assert total_v == pytest.approx(1497600)
    dev_id_evento = con.execute(
        "SELECT oficio_devolucion_id FROM preaud_factura_eventos WHERE factura='HUS0000541371'"
    ).fetchone()[0]
    assert dev_id_evento is not None
    dev_id_factura = con.execute(
        "SELECT oficio_devolucion_id FROM preaud_facturas WHERE factura='HUS0000541371'"
    ).fetchone()[0]
    assert dev_id_factura == dev_id_evento
    con.close()


def test_fuera_de_rango_y_sin_evento_se_saltan(db, tmp_path):
    xlsx = _excel(
        tmp_path,
        [
            (
                "DEV-PRE-AUD-0050-2026",
                "18/06/2026",
                [("111", "HUS0000541371", "1.000", "FHUS-AS-I01000-26", "VIEJO")],
            ),
            (
                "DEV-PRE-AUD-0104-2026",
                "4/08/2026",
                [
                    ("232018", "HUS0000999999", "500", "FHUS-AS-I01098-26", "SIN EVENTO"),
                    ("232018", "HUS0000888888", "500", "FHUS-AS-I01098-26", "NO EXISTE"),
                ],
            ),
        ],
    )
    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    # El bloque viejo queda fuera; el 0104 no amarra nada (sin evento / sin
    # factura) y por tanto NO se crea el oficio vacío.
    n = con.execute("SELECT COUNT(*) FROM preaud_oficios_devolucion").fetchone()[0]
    assert n == 0
    con.close()


def test_idempotente(db, tmp_path):
    xlsx = _excel(tmp_path, [BLOQUE_0104])
    _correr(xlsx, db, aplicar=True)
    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM preaud_oficios_devolucion").fetchone()[0]
    assert n == 1
    con.close()


def test_solo_mirar_no_escribe(db, tmp_path):
    xlsx = _excel(tmp_path, [BLOQUE_0104])
    _correr(xlsx, db, aplicar=False)
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM preaud_oficios_devolucion").fetchone()[0]
    assert n == 0
    con.close()
