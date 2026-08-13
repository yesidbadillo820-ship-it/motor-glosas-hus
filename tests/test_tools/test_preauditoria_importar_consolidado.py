"""Pruebas del importador del consolidado histórico de pre-auditoría.

Cubren las reglas de traducción del Excel del equipo (una fila por pasada)
al modelo canónico del módulo, el respeto por lo que ya está en la base
(el sistema manda) y la idempotencia (correr dos veces no duplica).
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

RAIZ = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location(
    "preauditoria_importar_consolidado",
    RAIZ / "tools" / "preauditoria_importar_consolidado.py",
)
imp = importlib.util.module_from_spec(spec)
sys.modules["preauditoria_importar_consolidado"] = imp
spec.loader.exec_module(imp)

ENCABEZADO = [
    "ITEM",
    "F_RECIBIDO",
    "ENVIO ",
    "AUDITOR",
    "FACTURA",
    "F_FACTURA",
    "VALOR",
    "NIT",
    "ENTIDAD",
    "CORREO F.E.",
    "PREAUDITORIA RADICACION SINAC",
    "RADICAR_1",
    "OBSERVACIONES ADICIONALES",
    "F_DEV",
    "F_REINSPECCIÓN",
    "OBSERVACIONES",
    "RADICAR_2",
    "NºOFICIO FACTURACION",
]


def _excel(tmp_path: Path, filas: list[list]) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    ws.append(ENCABEZADO)
    for f in filas:
        ws.append(f)
    ruta = tmp_path / "consolidado.xlsx"
    wb.save(ruta)
    return str(ruta)


@pytest.fixture()
def db(tmp_path):
    """Base SQLite con el esquema real del módulo (desde los modelos)."""
    from sqlalchemy import create_engine
    from app.models.db import Base

    ruta = tmp_path / "motorglosas.db"
    engine = create_engine(f"sqlite:///{ruta}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return str(ruta)


def _fila(
    item,
    factura,
    envio,
    radicar1,
    *,
    f_dev=None,
    f_reinsp=None,
    radicar2=None,
    oficio=None,
    auditor="OSCAR ",
    recibido=datetime(2026, 4, 13),
):
    return [
        item,
        recibido,
        envio,
        auditor,
        factura,
        datetime(2026, 3, 24),
        100000,
        "860002184",
        "AXA COLPATRIA ",
        "SI",
        "obs preauditoria",
        radicar1,
        None,
        f_dev,
        f_reinsp,
        None,
        radicar2,
        oficio,
    ]


def _correr(ruta_excel, ruta_db, aplicar=False):
    argv = ["prog", ruta_excel] + (["aplicar"] if aplicar else []) + [ruta_db]
    viejo = sys.argv
    sys.argv = argv
    try:
        assert imp.main() == 0
    finally:
        sys.argv = viejo


def test_radicada_simple(db, tmp_path):
    xlsx = _excel(tmp_path, [_fila(1, "HUS001", 111, "SI", oficio="FHUS-AS-I00500-26")])
    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    fila = con.execute(
        "SELECT estado, resultado_actual, num_devoluciones, auditor, oficio_fhus "
        "FROM preaud_facturas WHERE factura='HUS001'"
    ).fetchone()
    assert fila == ("RADICADA", "RADICAR", 0, "OSCAR VILLAMIZAR", "FHUS-AS-I00500-26")
    eventos = [
        r[0]
        for r in con.execute(
            "SELECT tipo_evento FROM preaud_factura_eventos WHERE factura='HUS001' ORDER BY id"
        )
    ]
    assert eventos == ["ESCRITA", "RADICADA"]
    con.close()


def test_devuelta_reinspeccion_y_radicada_en_la_misma_fila(db, tmp_path):
    xlsx = _excel(
        tmp_path,
        [
            _fila(
                1, "HUS002", 222, "SI", f_dev=datetime(2026, 4, 16), f_reinsp=datetime(2026, 4, 20)
            ),
        ],
    )
    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    estado, resultado, num_dev = con.execute(
        "SELECT estado, resultado_actual, num_devoluciones FROM preaud_facturas "
        "WHERE factura='HUS002'"
    ).fetchone()
    assert (estado, resultado, num_dev) == ("SUBSANADA", "RADICAR", 1)
    eventos = [
        r[0]
        for r in con.execute(
            "SELECT tipo_evento FROM preaud_factura_eventos WHERE factura='HUS002' ORDER BY id"
        )
    ]
    assert eventos == ["ESCRITA", "DEVUELTA", "REINGRESO", "SUBSANADA"]
    con.close()


def test_dos_pasadas_por_dos_envios(db, tmp_path):
    xlsx = _excel(
        tmp_path,
        [
            _fila(
                1, "HUS003", 111, "NO", f_dev=datetime(2026, 4, 16), recibido=datetime(2026, 4, 13)
            ),
            _fila(9, "HUS003", 333, "SI", recibido=datetime(2026, 5, 2)),
        ],
    )
    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    estado, resultado, envio, num_dev = con.execute(
        "SELECT estado, resultado_actual, envio_actual, num_devoluciones "
        "FROM preaud_facturas WHERE factura='HUS003'"
    ).fetchone()
    assert (estado, resultado, envio, num_dev) == ("SUBSANADA", "RADICAR", "333", 1)
    eventos = [
        r[0]
        for r in con.execute(
            "SELECT tipo_evento FROM preaud_factura_eventos WHERE factura='HUS003' ORDER BY id"
        )
    ]
    assert eventos == ["ESCRITA", "DEVUELTA", "REINGRESO", "SUBSANADA"]
    # Ledger: el envío 111 y el 333, cada uno contra su oficio sintético HIST-
    ledger = con.execute("SELECT COUNT(*) FROM preaud_envios_cargados").fetchone()[0]
    assert ledger == 2
    con.close()


def test_radicar2_con_fecha_cuenta_como_si(db, tmp_path):
    xlsx = _excel(
        tmp_path,
        [
            _fila(
                1,
                "HUS004",
                444,
                "NO",
                f_dev=datetime(2026, 5, 1),
                f_reinsp=datetime(2026, 5, 5),
                radicar2=datetime(2026, 5, 7),
            ),
        ],
    )
    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    estado, resultado = con.execute(
        "SELECT estado, resultado_actual FROM preaud_facturas WHERE factura='HUS004'"
    ).fetchone()
    assert (estado, resultado) == ("SUBSANADA", "RADICAR")
    con.close()


def test_no_toca_facturas_existentes(db, tmp_path):
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO preaud_facturas (factura, estado, resultado_actual, "
        "ronda_actual, num_subsanacion, num_devoluciones, pendiente_subsanacion, "
        "creado_por) VALUES ('HUS005', 'RADICADA', 'RADICAR', 1, 0, 0, 0, 'la-pagina')"
    )
    con.commit()
    con.close()
    xlsx = _excel(tmp_path, [_fila(1, "HUS005", 555, "NO", f_dev=datetime(2026, 4, 16))])
    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    estado, creado_por = con.execute(
        "SELECT estado, creado_por FROM preaud_facturas WHERE factura='HUS005'"
    ).fetchone()
    assert (estado, creado_por) == ("RADICADA", "la-pagina")  # intacta
    eventos = con.execute(
        "SELECT COUNT(*) FROM preaud_factura_eventos WHERE factura='HUS005'"
    ).fetchone()[0]
    assert eventos == 0  # ni un evento inventado sobre lo que ya existía
    con.close()


def test_idempotente(db, tmp_path):
    xlsx = _excel(
        tmp_path,
        [
            _fila(1, "HUS006", 666, "SI", oficio="FHUS-AS-I00600-26"),
            _fila(2, "HUS007", 666, "NO", f_dev=datetime(2026, 4, 16), oficio="FHUS-AS-I00600-26"),
        ],
    )
    _correr(xlsx, db, aplicar=True)
    _correr(xlsx, db, aplicar=True)  # segunda corrida: no debe duplicar nada
    con = sqlite3.connect(db)
    for tabla, esperado in [
        ("preaud_facturas", 2),
        ("preaud_oficios_recepcion", 1),
        ("preaud_envios_cargados", 1),
        ("preaud_fuente_radicacion", 2),
    ]:
        n = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        assert n == esperado, f"{tabla}: {n} != {esperado}"
    eventos = con.execute("SELECT COUNT(*) FROM preaud_factura_eventos").fetchone()[0]
    assert eventos == 4  # ESCRITA+RADICADA y ESCRITA+DEVUELTA, una sola vez
    con.close()


def test_solo_mirar_no_escribe(db, tmp_path):
    xlsx = _excel(tmp_path, [_fila(1, "HUS008", 888, "SI")])
    _correr(xlsx, db, aplicar=False)
    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM preaud_facturas").fetchone()[0]
    assert n == 0
    con.close()
