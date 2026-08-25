"""Pruebas del comando que revisa un envío y señala las facturas rezagadas.

El caso que lo originó (19-08-2026, envío 232047): la fuente de Radicación
arrastraba una factura de un cargue anterior y la página la traía al oficio
aunque el DGH ya no la mostraba en ese envío.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location(
    "preauditoria_revisar_envio", RAIZ / "tools" / "preauditoria_revisar_envio.py"
)
imp = importlib.util.module_from_spec(spec)
sys.modules["preauditoria_revisar_envio"] = imp
spec.loader.exec_module(imp)


@pytest.fixture()
def db(tmp_path):
    from sqlalchemy import create_engine

    from app.models.db import Base

    ruta = tmp_path / "motorglosas.db"
    engine = create_engine(f"sqlite:///{ruta}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return str(ruta)


def _fuente(con, factura, envio, valor, cuando, archivo):
    con.execute(
        "INSERT INTO preaud_fuente_radicacion "
        "(factura, envio, valor, fuente_archivo, importado_en, actualizado_en) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (factura, envio, valor, archivo, cuando, cuando),
    )


def _correr(db, envio, capsys):
    viejo = sys.argv
    sys.argv = ["prog", envio, db]
    try:
        assert imp.main() == 0
    finally:
        sys.argv = viejo
    return capsys.readouterr().out


def test_senala_la_factura_que_quedo_de_un_cargue_viejo(db, capsys):
    con = sqlite3.connect(db)
    _fuente(con, "HUS0000538527", "232047", 75400, "2026-08-19 10:00:00", "rad_19ago.xlsx")
    _fuente(con, "HUS0000538538", "232047", 435500, "2026-08-19 10:00:00", "rad_19ago.xlsx")
    _fuente(con, "HUS0000538528", "232047", 442900, "2026-07-28 09:00:00", "rad_28jul.xlsx")
    con.execute(
        "INSERT INTO preaud_facturas (factura, envio_actual, oficio_fhus, estado, "
        "resultado_actual, ronda_actual, num_subsanacion, num_devoluciones, "
        "pendiente_subsanacion) VALUES ('HUS0000538528', '232047', 'FHUS-AS-I01188-26', "
        "'NUEVA', 'PENDIENTE', 1, 0, 0, 0)"
    )
    con.commit()
    con.close()

    salida = _correr(db, "232047", capsys)
    assert "3 factura(s) en la fuente" in salida
    assert "HUS0000538528" in salida and "<-- OJO" in salida
    assert "FHUS-AS-I01188-26 (NUEVA)" in salida  # dice dónde quedó cargada
    assert "1 factura(s) quedaron de un cargue ANTERIOR" in salida
    # Las del cargue bueno no se señalan.
    assert salida.count("<-- OJO") == 1


def test_todas_del_mismo_cargue_no_avisa(db, capsys):
    con = sqlite3.connect(db)
    _fuente(con, "HUS0000538527", "232047", 75400, "2026-08-19 10:00:00", "rad.xlsx")
    _fuente(con, "HUS0000538538", "232047", 435500, "2026-08-19 10:30:00", "rad.xlsx")
    con.commit()
    con.close()

    salida = _correr(db, "232047", capsys)
    assert "no hay facturas rezagadas" in salida
    assert "OJO" not in salida


def test_envio_que_no_existe(db, capsys):
    salida = _correr(db, "999999", capsys)
    assert "no está en la fuente" in salida


def test_no_escribe_en_la_base(db, capsys):
    con = sqlite3.connect(db)
    _fuente(con, "HUS0000538527", "232047", 75400, "2026-08-19 10:00:00", "rad.xlsx")
    con.commit()
    con.close()
    antes = Path(db).read_bytes()
    _correr(db, "232047", capsys)
    assert Path(db).read_bytes() == antes
