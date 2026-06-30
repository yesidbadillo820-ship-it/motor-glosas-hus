"""Tests del Tablero de Radicación y Cartera (tools/tablero_cartera.py).

Cubre: parseo de valores COP y fechas, los derivados de cartera (saldo,
objetado, % recaudo, estado, mora/aging), la lectura de la radicación y del
seguimiento, la fusión por factura, las agregaciones del tablero y el render
del HTML autocontenido.
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

# Los scripts viven en tools/ (sin __init__.py): los importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import tablero_cartera as tab  # noqa: E402
from _tablero_html import render_html  # noqa: E402

# ─── Parseo ──────────────────────────────────────────────────────────────────


class TestParseo:
    def test_valor_numero(self):
        assert tab._parse_valor(5000) == 5000.0
        assert tab._parse_valor(1234.5) == 1234.5

    def test_valor_cop_miles_y_decimal(self):
        assert tab._parse_valor("$ 1.234.567,89") == 1234567.89

    def test_valor_solo_miles(self):
        assert tab._parse_valor("1.234.567") == 1234567.0

    def test_valor_vacio(self):
        assert tab._parse_valor("") == 0.0
        assert tab._parse_valor(None) == 0.0

    def test_fecha_formatos(self):
        assert tab._parse_fecha("2026-06-30") == date(2026, 6, 30)
        assert tab._parse_fecha("30/06/2026") == date(2026, 6, 30)
        assert tab._parse_fecha("") is None


# ─── Derivados de la factura ────────────────────────────────────────────────


class TestFacturaCartera:
    def _f(self, **kw):
        base = {"factura": "HUS100", "factura_norm": "100", "valor_radicado": 1_000_000.0}
        base.update(kw)
        return tab.FacturaCartera(**base)

    def test_saldo_y_recaudo(self):
        f = self._f(valor_pagado=400_000.0)
        assert f.saldo == 600_000.0
        assert f.pct_recaudo == 40.0

    def test_objetado_y_en_tramite(self):
        f = self._f(valor_glosado=200_000.0, valor_devuelto=50_000.0, valor_pagado=100_000.0)
        assert f.objetado == 250_000.0
        # saldo 900k, objetado 250k → en trámite 650k
        assert f.en_tramite == 650_000.0

    def test_estado_pagada(self):
        f = self._f(valor_pagado=1_000_000.0, fecha_radicacion=date(2026, 3, 1))
        assert f.estado_cartera == "PAGADA"

    def test_estado_pago_parcial(self):
        f = self._f(valor_pagado=300_000.0, fecha_radicacion=date(2026, 3, 1))
        assert f.estado_cartera == "PAGO_PARCIAL"

    def test_estado_glosada(self):
        f = self._f(valor_glosado=300_000.0, fecha_radicacion=date(2026, 3, 1))
        assert f.estado_cartera == "GLOSADA_DEVUELTA"

    def test_estado_pendiente_radicar(self):
        f = self._f()  # sin fecha_radicacion
        assert f.estado_cartera == "PENDIENTE_RADICAR"

    def test_mora_y_tramo(self):
        f = self._f(fecha_radicacion=date(2026, 5, 1))  # saldo>0
        corte = date(2026, 6, 30)
        assert f.dias_mora(corte) == 60
        assert f.tramo_mora(corte) == "31-60"

    def test_mora_none_si_pagada(self):
        f = self._f(valor_pagado=1_000_000.0, fecha_radicacion=date(2026, 5, 1))
        assert f.dias_mora(date(2026, 6, 30)) is None  # saldo 0 → sin mora


# ─── Carga + fusión + agregación ─────────────────────────────────────────────


def _csv(ruta: Path, filas: list[list]) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(filas)


class TestCargaYAgregacion:
    def _radicacion(self, tmp_path) -> Path:
        r = tmp_path / "rad.csv"
        _csv(
            r,
            [
                ["factura", "entidad", "entidad_id", "canal", "valor_total", "estado"],
                ["HUS100", "COOSALUD EPS", "COOSALUD", "PORTAL_BOT", "1000000", "LISTA"],
                ["HUS200", "NUEVA EPS", "NUEVA_EPS", "PORTAL", "2000000", "LISTA"],
                ["HUS300", "NUEVA EPS", "NUEVA_EPS", "PORTAL", "500000", "REVISAR_TIPIFICACION"],
            ],
        )
        return r

    def test_cargar_radicacion(self, tmp_path):
        inv = tab.cargar_radicacion([self._radicacion(tmp_path)])
        assert set(inv) == {"100", "200", "300"}
        assert inv["200"].valor_radicado == 2_000_000.0
        assert inv["200"].entidad == "NUEVA EPS"

    def test_seguimiento_headers_flexibles(self, tmp_path):
        s = tmp_path / "seg.csv"
        _csv(
            s,
            [
                ["Factura", "Fecha Radicacion", "Glosa", "Pagado"],
                ["HUS100", "2026-05-01", "100000", "400000"],
            ],
        )
        seg = tab.cargar_seguimiento(s)
        assert seg["100"]["valor_glosado"] == 100_000.0
        assert seg["100"]["valor_pagado"] == 400_000.0
        assert seg["100"]["fecha_radicacion"] == date(2026, 5, 1)

    def test_fusion_y_agregacion(self, tmp_path):
        inv = tab.cargar_radicacion([self._radicacion(tmp_path)])
        s = tmp_path / "seg.csv"
        _csv(
            s,
            [
                ["FACTURA", "FECHA_RADICACION", "VALOR_GLOSADO", "VALOR_PAGADO", "MOTIVO_GLOSA"],
                ["HUS100", "2026-05-01", "0", "1000000", ""],  # pagada
                ["HUS200", "2026-04-01", "300000", "0", "Tarifa no pactada"],  # glosada
            ],
        )
        facturas = tab.fusionar(inv, tab.cargar_seguimiento(s))
        datos = tab.agregar(facturas, date(2026, 6, 30))
        k = datos["kpis"]
        assert k["n_facturas"] == 3
        assert k["radicado"] == 3_500_000.0
        assert k["pagado"] == 1_000_000.0
        assert k["glosado"] == 300_000.0
        assert k["saldo"] == 2_500_000.0  # 3.5M - 1M pagado
        assert k["n_pagadas"] == 1
        # NUEVA EPS agrupa HUS200 + HUS300
        nueva = next(e for e in datos["entidades"] if e["entidad"] == "NUEVA EPS")
        assert nueva["n"] == 2
        assert nueva["radicado"] == 2_500_000.0
        # Motivos de glosa
        assert datos["motivos"][0]["motivo"] == "Tarifa no pactada"
        # Aging: HUS200 con saldo y radicada 2026-04-01 → 90 días al corte
        assert datos["aging"]["61-90"] == 2_000_000.0

    def test_seguimiento_de_factura_inexistente_se_ignora(self, tmp_path):
        inv = tab.cargar_radicacion([self._radicacion(tmp_path)])
        s = tmp_path / "seg.csv"
        _csv(s, [["FACTURA", "VALOR_PAGADO"], ["HUS999", "5000"]])
        facturas = tab.fusionar(inv, tab.cargar_seguimiento(s))
        assert len(facturas) == 3  # la 999 no se agrega


# ─── Render del HTML ─────────────────────────────────────────────────────────


class TestRender:
    def test_html_autocontenido_con_datos(self, tmp_path):
        inv = tab.cargar_radicacion(
            [
                self._mk(
                    tmp_path,
                    [
                        ["factura", "entidad", "entidad_id", "valor_total", "estado"],
                        ["HUS100", "COOSALUD EPS", "COOSALUD", "1000000", "LISTA"],
                    ],
                )
            ]
        )
        datos = tab.agregar(list(inv.values()), date(2026, 6, 30))
        datos["titulo"] = "Prueba HUS"
        html = render_html(datos)
        assert "<!DOCTYPE html>" in html
        assert "Prueba HUS" in html
        assert "COOSALUD EPS" in html
        assert "__DATA__" not in html  # el marcador se reemplazó
        assert "const DATA =" in html

    def _mk(self, tmp_path, filas):
        r = tmp_path / "rad.csv"
        _csv(r, filas)
        return r


def test_crear_plantilla(tmp_path):
    import importlib.util

    if importlib.util.find_spec("openpyxl") is None:
        import pytest

        pytest.skip("openpyxl no instalado")
    f = tab.FacturaCartera(
        factura="HUS100", factura_norm="100", entidad="COOSALUD EPS", valor_radicado=1_000_000.0
    )
    ruta = tmp_path / "plantilla.xlsx"
    tab.crear_plantilla([f], ruta)
    assert ruta.is_file()
    filas = tab._leer_tabla(ruta)
    assert filas[0] == tab.COLS_PLANTILLA
    assert filas[1][0] == "HUS100"
    assert filas[1][2] == 1_000_000.0
