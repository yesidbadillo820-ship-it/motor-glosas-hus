"""Pruebas del comando que compara un acta/Excel contra lo que ya sabe el sistema.

El caso que lo originó (20-08-2026): llegó la hoja del oficio FHUS-AS-I01162-26
con las decisiones del 18 de agosto y la pregunta fue «¿esto ya está subido?».
El comando responde factura por factura y NO cambia nada.
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
    "preauditoria_comparar_acta", RAIZ / "tools" / "preauditoria_comparar_acta.py"
)
cmp_acta = importlib.util.module_from_spec(spec)
sys.modules["preauditoria_comparar_acta"] = cmp_acta
spec.loader.exec_module(cmp_acta)

ENCABEZADO = [
    "ITEM",
    "F_RECIBIDO",
    "ENVIO",
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


def _fila(item, envio, factura, radicar_1, f_dev=None, oficio="FHUS-AS-I01162-26"):
    return [
        item,
        datetime(2026, 8, 13),
        envio,
        "VANESSA",
        factura,
        datetime(2026, 7, 30),
        99900,
        "860037013",
        "COMPAÑIA MUNDIAL DE SEGUROS",
        "SI",
        "SOPORTES",
        radicar_1,
        "",
        f_dev,
        None,
        "",
        "",
        oficio,
    ]


@pytest.fixture()
def excel(tmp_path):
    def _crear(filas):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Hoja1"
        ws.append(ENCABEZADO)
        for f in filas:
            ws.append(f)
        ruta = tmp_path / "acta.xlsx"
        wb.save(ruta)
        return str(ruta)

    return _crear


@pytest.fixture()
def db(tmp_path):
    from sqlalchemy import create_engine

    from app.models.db import Base

    ruta = tmp_path / "motorglosas.db"
    engine = create_engine(f"sqlite:///{ruta}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return str(ruta)


def _factura(ruta_db, factura, estado, resultado, num_dev=0, oficio="FHUS-AS-I01162-26"):
    con = sqlite3.connect(ruta_db)
    con.execute(
        "INSERT INTO preaud_facturas (factura, envio_actual, oficio_fhus, estado, "
        "resultado_actual, ronda_actual, num_subsanacion, num_devoluciones, "
        "pendiente_subsanacion, creado_por) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (factura, "232619", oficio, estado, resultado, 1, 0, num_dev, 0, "prueba"),
    )
    con.commit()
    con.close()


def _correr(capsys, ruta_excel, ruta_db):
    sys.argv = ["preauditoria_comparar_acta.py", ruta_excel, ruta_db]
    assert cmp_acta.main() == 0
    return capsys.readouterr().out


class TestVeredicto:
    """La regla, sin pasar por el Excel ni por la base."""

    def test_la_decision_que_falta_se_marca(self):
        sis = {"estado": "NUEVA", "resultado": "PENDIENTE", "num_dev": 0, "oficio": "FHUS-1"}
        marca, texto = cmp_acta.veredicto("DEVUELTA", True, sis)
        assert marca == "FALTA"
        assert "devuélvala en la página" in texto

    def test_lo_que_ya_esta_igual_no_pide_nada(self):
        sis = {"estado": "RADICADA", "resultado": "RADICAR", "num_dev": 0, "oficio": "FHUS-1"}
        assert cmp_acta.veredicto("RADICAR", False, sis)[0] == "AL DÍA"

    def test_si_el_sistema_ya_siguio_no_es_un_faltante(self):
        """El acta la muestra devuelta y en la página ya reingresó a otro oficio."""
        sis = {
            "estado": "EN_SUBSANACION",
            "resultado": "PENDIENTE",
            "num_dev": 1,
            "oficio": "FHUS-AS-I01190-26",
        }
        marca, texto = cmp_acta.veredicto("DEVUELTA", True, sis)
        assert marca == "ADELANTE"
        assert "FHUS-AS-I01190-26" in texto

    def test_contradiccion_se_marca_diferente(self):
        sis = {
            "estado": "DEVUELTA_PEND_SUBSANACION",
            "resultado": "DEVUELTA",
            "num_dev": 1,
            "oficio": "FHUS-1",
        }
        assert cmp_acta.veredicto("RADICAR", False, sis)[0] == "DIFERENTE"

    def test_la_que_no_existe_se_marca(self):
        marca, texto = cmp_acta.veredicto("RADICAR", False, None)
        assert marca == "NO ESTÁ"
        assert "escriba su envío" in texto


class TestComandoCompleto:
    def test_dice_cuales_faltan_y_cuales_ya_estan(self, capsys, excel, db):
        ruta = excel(
            [
                _fila(1, "232619", "HUS0000544836", "NO", datetime(2026, 8, 18)),
                _fila(2, "232620", "HUS0000544837", "SI"),
                _fila(3, "232621", "HUS0000544838", "SI"),
            ]
        )
        _factura(db, "HUS0000544836", "NUEVA", "PENDIENTE")  # falta la devolución
        _factura(db, "HUS0000544837", "RADICADA", "RADICAR")  # al día
        # HUS0000544838 no existe en la base
        salida = _correr(capsys, ruta, db)
        assert "HUS0000544836" in salida and "FALTA" in salida
        assert "AL DÍA" in salida
        assert "NO ESTÁ" in salida
        assert "3 factura(s) en el Excel" in salida or "3 fila(s)" in salida

    def test_cuando_todo_esta_cargado_lo_dice_claro(self, capsys, excel, db):
        ruta = excel([_fila(1, "232620", "HUS0000544837", "SI")])
        _factura(db, "HUS0000544837", "RADICADA", "RADICAR")
        salida = _correr(capsys, ruta, db)
        assert "ya está en el sistema: no hay nada que cargar" in salida
        assert "piden acción" not in salida

    def test_no_toca_la_base(self, capsys, excel, db):
        ruta = excel([_fila(1, "232619", "HUS0000544836", "NO", datetime(2026, 8, 18))])
        _factura(db, "HUS0000544836", "NUEVA", "PENDIENTE")
        _correr(capsys, ruta, db)
        con = sqlite3.connect(db)
        fila = con.execute(
            "SELECT estado, resultado_actual FROM preaud_facturas WHERE factura=?",
            ("HUS0000544836",),
        ).fetchone()
        con.close()
        assert fila == ("NUEVA", "PENDIENTE")

    def test_base_inexistente_avisa_sin_reventar(self, capsys, excel, tmp_path):
        ruta = excel([_fila(1, "232619", "HUS0000544836", "NO")])
        sys.argv = ["x", ruta, str(tmp_path / "no_existe.db")]
        assert cmp_acta.main() == 1
        assert "No se encontró la base de datos" in capsys.readouterr().out
