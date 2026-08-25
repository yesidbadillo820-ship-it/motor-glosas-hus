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


def _eventos_de(con, factura):
    return [
        r[0]
        for r in con.execute(
            "SELECT tipo_evento FROM preaud_factura_eventos WHERE factura=? ORDER BY id",
            (factura,),
        )
    ]


def test_actualiza_factura_que_avanzo(db, tmp_path):
    """El equipo llenó RADICAR_1 después de la primera corrida: se agrega
    solo la cola nueva de eventos y el estado se pone al día."""
    xlsx1 = _excel(tmp_path, [_fila(1, "HUS010", 111, "")])
    _correr(xlsx1, db, aplicar=True)
    con = sqlite3.connect(db)
    assert (
        con.execute("SELECT estado FROM preaud_facturas WHERE factura='HUS010'").fetchone()[0]
        == "NUEVA"
    )
    assert _eventos_de(con, "HUS010") == ["ESCRITA"]
    con.close()

    (tmp_path / "v2").mkdir()
    xlsx2 = _excel(tmp_path / "v2", [_fila(1, "HUS010", 111, "SI", oficio="FHUS-AS-I00700-26")])
    _correr(xlsx2, db, aplicar=True)
    _correr(xlsx2, db, aplicar=True)  # segunda corrida: ya está al día, no duplica
    con = sqlite3.connect(db)
    estado, oficio = con.execute(
        "SELECT estado, oficio_fhus FROM preaud_facturas WHERE factura='HUS010'"
    ).fetchone()
    assert (estado, oficio) == ("RADICADA", "FHUS-AS-I00700-26")
    assert _eventos_de(con, "HUS010") == ["ESCRITA", "RADICADA"]
    n = con.execute("SELECT COUNT(*) FROM preaud_facturas WHERE factura='HUS010'").fetchone()[0]
    assert n == 1
    con.close()


def test_actualiza_con_pasada_nueva(db, tmp_path):
    """La factura devuelta reapareció en otro envío y quedó radicada."""
    fila1 = _fila(
        1, "HUS011", 111, "NO", f_dev=datetime(2026, 8, 4), recibido=datetime(2026, 7, 30)
    )
    xlsx1 = _excel(tmp_path, [fila1])
    _correr(xlsx1, db, aplicar=True)

    (tmp_path / "v2").mkdir()
    fila2 = _fila(9, "HUS011", 222, "SI", recibido=datetime(2026, 8, 6))
    xlsx2 = _excel(tmp_path / "v2", [fila1, fila2])
    _correr(xlsx2, db, aplicar=True)
    con = sqlite3.connect(db)
    estado, resultado, envio, num_dev = con.execute(
        "SELECT estado, resultado_actual, envio_actual, num_devoluciones "
        "FROM preaud_facturas WHERE factura='HUS011'"
    ).fetchone()
    assert (estado, resultado, envio, num_dev) == ("SUBSANADA", "RADICAR", "222", 1)
    assert _eventos_de(con, "HUS011") == ["ESCRITA", "DEVUELTA", "REINGRESO", "SUBSANADA"]
    # Los eventos viejos no se tocaron (siguen con la marca del import)
    marcas = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT creado_por FROM preaud_factura_eventos WHERE factura='HUS011'"
        )
    }
    assert marcas == {"importacion-historica-excel"}
    con.close()


def test_conflicto_no_se_toca(db, tmp_path):
    """Si la historia del Excel ya no encaja como continuación (corrigieron
    un SI por un NO), la factura no se toca."""
    xlsx1 = _excel(tmp_path, [_fila(1, "HUS012", 111, "SI")])
    _correr(xlsx1, db, aplicar=True)

    (tmp_path / "v2").mkdir()
    xlsx2 = _excel(tmp_path / "v2", [_fila(1, "HUS012", 111, "NO", f_dev=datetime(2026, 8, 4))])
    _correr(xlsx2, db, aplicar=True)
    con = sqlite3.connect(db)
    assert (
        con.execute("SELECT estado FROM preaud_facturas WHERE factura='HUS012'").fetchone()[0]
        == "RADICADA"
    )
    assert _eventos_de(con, "HUS012") == ["ESCRITA", "RADICADA"]
    con.close()


def test_radicar2_con_fecha_completa_la_devolucion_sin_conflicto(db, tmp_path):
    """Práctica real del equipo: RADICAR_1=NO sin fechas, y tiempo después
    anotan la fecha de radicación en RADICAR_2. La devolución del pasado
    debe conservarse y la factura terminar SUBSANADA — nunca en conflicto."""
    xlsx1 = _excel(tmp_path, [_fila(1, "HUS014", 111, "NO")])
    _correr(xlsx1, db, aplicar=True)
    con = sqlite3.connect(db)
    assert _eventos_de(con, "HUS014") == ["ESCRITA", "DEVUELTA"]
    con.close()

    (tmp_path / "v2").mkdir()
    xlsx2 = _excel(tmp_path / "v2", [_fila(1, "HUS014", 111, "NO", radicar2=datetime(2026, 8, 12))])
    _correr(xlsx2, db, aplicar=True)
    con = sqlite3.connect(db)
    estado, motivo = con.execute(
        "SELECT estado, motivo_ultima_devolucion FROM preaud_facturas WHERE factura='HUS014'"
    ).fetchone()
    assert estado == "SUBSANADA"
    assert motivo is None  # al quedar radicada, el motivo de devolución se limpia
    assert _eventos_de(con, "HUS014") == ["ESCRITA", "DEVUELTA", "SUBSANADA"]
    con.close()


def test_sana_encabezado_sin_duplicar_eventos(db, tmp_path):
    """Si el encabezado quedó mal por una corrida vieja (misma historia),
    se corrige solo, sin agregar eventos."""
    xlsx = _excel(tmp_path, [_fila(1, "HUS015", 111, "NO", f_dev=datetime(2026, 8, 4))])
    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    con.execute("UPDATE preaud_facturas SET estado='NUEVA', ronda_actual=9 WHERE factura='HUS015'")
    con.commit()
    con.close()

    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    estado, ronda = con.execute(
        "SELECT estado, ronda_actual FROM preaud_facturas WHERE factura='HUS015'"
    ).fetchone()
    assert (estado, ronda) == ("DEVUELTA_PEND_SUBSANACION", 1)
    assert _eventos_de(con, "HUS015") == ["ESCRITA", "DEVUELTA"]
    con.close()


def test_reenvio_sin_decision_queda_en_subsanacion(db, tmp_path):
    """Una fila nueva de reenvío sin RADICAR todavía: la factura queda
    EN_SUBSANACION (no retrocede a NUEVA)."""
    fila1 = _fila(1, "HUS016", 111, "NO", f_dev=datetime(2026, 8, 4))
    xlsx1 = _excel(tmp_path, [fila1])
    _correr(xlsx1, db, aplicar=True)

    (tmp_path / "v2").mkdir()
    xlsx2 = _excel(
        tmp_path / "v2", [fila1, _fila(9, "HUS016", 222, "", recibido=datetime(2026, 8, 8))]
    )
    _correr(xlsx2, db, aplicar=True)
    con = sqlite3.connect(db)
    estado, dev_id = con.execute(
        "SELECT estado, oficio_devolucion_id FROM preaud_facturas WHERE factura='HUS016'"
    ).fetchone()
    assert estado == "EN_SUBSANACION"
    assert dev_id is None  # el reingreso limpia el amarre al oficio de devolución
    assert _eventos_de(con, "HUS016") == ["ESCRITA", "DEVUELTA", "REINGRESO"]
    con.close()


def test_reingreso_limpia_amarre_a_oficio_devolucion(db, tmp_path):
    """La página generó el oficio de devolución (selló el evento y marcó la
    factura); cuando el Excel trae el reingreso, el amarre del encabezado se
    limpia como lo hace la página, y el evento sellado NO se toca."""
    fila1 = _fila(1, "HUS017", 111, "NO", f_dev=datetime(2026, 8, 4))
    xlsx1 = _excel(tmp_path, [fila1])
    _correr(xlsx1, db, aplicar=True)
    con = sqlite3.connect(db)
    con.executescript(
        """
        INSERT INTO preaud_oficios_devolucion (consecutivo, anio, numero,
            fecha_generado, total_facturas, total_valor)
        VALUES ('DEV-PRE-AUD-0001-2026', 2026, 1, '2026-08-05 08:00:00', 1, 100000);
        UPDATE preaud_facturas SET oficio_devolucion_id=1 WHERE factura='HUS017';
        UPDATE preaud_factura_eventos SET oficio_devolucion_id=1
         WHERE factura='HUS017' AND tipo_evento='DEVUELTA';
        """
    )
    con.commit()
    con.close()

    (tmp_path / "v2").mkdir()
    xlsx2 = _excel(
        tmp_path / "v2",
        [
            _fila(
                1,
                "HUS017",
                111,
                "NO",
                f_dev=datetime(2026, 8, 4),
                f_reinsp=datetime(2026, 8, 9),
                radicar2=datetime(2026, 8, 11),
            )
        ],
    )
    _correr(xlsx2, db, aplicar=True)
    con = sqlite3.connect(db)
    dev_id, estado = con.execute(
        "SELECT oficio_devolucion_id, estado FROM preaud_facturas WHERE factura='HUS017'"
    ).fetchone()
    assert dev_id is None
    assert estado == "SUBSANADA"
    sellado = con.execute(
        "SELECT oficio_devolucion_id FROM preaud_factura_eventos "
        "WHERE factura='HUS017' AND tipo_evento='DEVUELTA'"
    ).fetchone()[0]
    assert sellado == 1  # el evento sellado por la página sigue intacto
    con.close()


ENCABEZADO_ADRES = [
    "Oficio",
    "Item",
    "Fecha _Recibido",
    "Envío",
    "AUD",
    "HUS",
    "Fecha_Factura",
    "Valor",
    "NIT",
    "Entidad",
    "Correo F.E.",
    "Observación Preauditoria Radicación",
    "Radicar_1",
    "Observaciones Adicionales",
    "Fecha_Entrega_Fact",
    "Observación_FACTURACIÓN",
    "Fecha_Dev_CARTERA",
    "Fecha_Segunda_Revisión",
    "Segunda_Observación_SINAC",
    "Fecha_Dev_FACTURACIÓN",
    "Segunda_Observación_FACTURACIÓN",
    "Fecha_Dev_CARTERA",
    "Radicar_2",
    "Fecha_Radicación",
    "Número_Radicado",
    "INFOPOL",
]


def test_formato_adres_se_reconoce_solo(db, tmp_path):
    """El consolidado ADRES (hoja CONSOLIDADO, columna Oficio adelante) se
    traduce al mismo modelo, normalizando el número de oficio."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CONSOLIDADO"
    ws.append(ENCABEZADO_ADRES)
    base = [
        "FHUS- AS-101139-26",
        1993,
        datetime(2026, 7, 30),
        232114,
        "EC ",
        "HUS0000537334",
        datetime(2025, 10, 25),
        3743500,
        "901037916",
        "ADRES",
        "SI",
        "REVISAR CAMPO 83",
        "NO",
    ] + [None] * 13
    ws.append(base)
    fila2 = list(base)
    fila2[1], fila2[5], fila2[12] = 1994, "HUS0000500408", "SI"
    ws.append(fila2)
    ruta = tmp_path / "adres.xlsx"
    wb.save(ruta)

    _correr(str(ruta), db, aplicar=True)
    con = sqlite3.connect(db)
    estado, oficio, auditor = con.execute(
        "SELECT estado, oficio_fhus, auditor FROM preaud_facturas WHERE factura='HUS0000537334'"
    ).fetchone()
    assert estado == "DEVUELTA_PEND_SUBSANACION"
    assert oficio == "FHUS-AS-I01139-26"  # normalizado: sin espacios y con la I
    assert auditor == "ELIAS CARVAJAL"
    assert (
        con.execute("SELECT estado FROM preaud_facturas WHERE factura='HUS0000500408'").fetchone()[
            0
        ]
        == "RADICADA"
    )
    con.close()


def test_fila_duplicada_identica_se_ignora_con_aviso(db, tmp_path):
    fila = _fila(1, "HUS018", 111, "SI")
    xlsx = _excel(tmp_path, [fila, list(fila)])
    _correr(xlsx, db, aplicar=True)
    con = sqlite3.connect(db)
    assert _eventos_de(con, "HUS018") == ["ESCRITA", "RADICADA"]  # una sola pasada
    con.close()


def test_evento_de_la_pagina_bloquea_actualizacion(db, tmp_path):
    """Si la página ya tocó la factura (evento ajeno), el import no la pisa."""
    xlsx1 = _excel(tmp_path, [_fila(1, "HUS013", 111, "")])
    _correr(xlsx1, db, aplicar=True)
    con = sqlite3.connect(db)
    con.execute("UPDATE preaud_factura_eventos SET creado_por='la-pagina' WHERE factura='HUS013'")
    con.commit()
    con.close()

    (tmp_path / "v2").mkdir()
    xlsx2 = _excel(tmp_path / "v2", [_fila(1, "HUS013", 111, "SI")])
    _correr(xlsx2, db, aplicar=True)
    con = sqlite3.connect(db)
    assert (
        con.execute("SELECT estado FROM preaud_facturas WHERE factura='HUS013'").fetchone()[0]
        == "NUEVA"
    )
    assert _eventos_de(con, "HUS013") == ["ESCRITA"]
    con.close()
