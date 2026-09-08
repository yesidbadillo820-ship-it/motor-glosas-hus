"""Pruebas de las fuentes de radicacion de tools/respuesta_tramites_dgh.py.

La recepcion de DGH de una semana mezcla facturas de varios cargues viejos:
las fechas de radicacion ya no estan en UNA carpeta de cargue masivo sino
repartidas en consolidados y cabeceras de corridas anteriores. Estas pruebas
cubren el lector generico (cabecera del portal, CONSOLIDADO FACTURAS, hoja
BASE de un CONSOLIDADO RESPUESTAS) y la union de varias fuentes.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import respuesta_tramites_dgh as rt  # noqa: E402
from openpyxl import Workbook  # noqa: E402


def _xlsx(ruta: Path, encabezados: list[str], filas: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(encabezados)
    for f in filas:
        ws.append(f)
    wb.save(ruta)
    return ruta


class TestLectorGenerico:
    def test_cabecera_del_portal(self, tmp_path):
        p = _xlsx(
            tmp_path / "HUS543960.xlsx",
            ["numero_factura", "fecha_radicacion", "valor_total"],
            [["HUS543960", datetime(2026, 8, 4), 119500]],
        )
        assert rt.leer_radicaciones_archivo(p) == {"HUS543960": date(2026, 8, 4)}

    def test_consolidado_respuestas_estilo_base(self, tmp_path):
        # Encabezados como los deja consolidar_coosalud (FACTURA + FECHA RADICACION).
        p = _xlsx(
            tmp_path / "CONSOLIDADO RESPUESTAS.xlsx",
            ["FACTURA", "FECHA RADICACION", "FECHA GLOSA", "DIA"],
            [
                ["HUS0000531113", datetime(2026, 7, 2), datetime(2026, 8, 1), 20],
                ["HUS0000532848", "2026-07-06", None, None],
            ],
        )
        rad = rt.leer_radicaciones_archivo(p)
        assert rad["HUS531113"] == date(2026, 7, 2)
        assert rad["HUS532848"] == date(2026, 7, 6)

    def test_sin_columna_de_radicacion_devuelve_vacio(self, tmp_path):
        # "Numero Radicacion" solo NO alcanza: hace falta la FECHA de radicacion.
        p = _xlsx(
            tmp_path / "otro.xlsx",
            ["FACTURA", "Numero Radicacion", "VALOR"],
            [["HUS500000", "RAD-575798", 1]],
        )
        assert rt.leer_radicaciones_archivo(p) == {}


class TestUnionDeFuentes:
    def test_varias_fuentes_gana_la_primera(self, tmp_path):
        # Carpeta de cargue masivo con cabeceras (fuente 1).
        masivo = tmp_path / "CARGUE MASIVO COOSALUD"
        (masivo / "FACTURAS").mkdir(parents=True)
        _xlsx(
            masivo / "FACTURAS" / "HUS100.xlsx",
            ["numero_factura", "fecha_radicacion"],
            [["HUS100", datetime(2026, 8, 1)]],
        )
        # Consolidado viejo (fuente extra) con HUS100 (fecha distinta: debe
        # ganar la carpeta, que va primero) y HUS200 (nueva).
        extra = _xlsx(
            tmp_path / "CONSOLIDADO FACTURAS VIEJO.xlsx",
            ["FACTURA", "FECHA RADICACION"],
            [
                ["HUS0000000100", datetime(2026, 1, 1)],
                ["HUS200", datetime(2026, 7, 15)],
            ],
        )
        rad = rt.cargar_radicaciones_fuentes([masivo], [extra])
        assert rad["HUS100"] == date(2026, 8, 1)  # gano la carpeta del masivo
        assert rad["HUS200"] == date(2026, 7, 15)

    def test_carpeta_extra_recorre_sus_xlsx(self, tmp_path):
        carpeta = tmp_path / "CONSOLIDADOS VIEJOS"
        carpeta.mkdir()
        _xlsx(
            carpeta / "uno.xlsx",
            ["FACTURA", "FECHA RADICACION"],
            [["HUS300", datetime(2026, 6, 10)]],
        )
        _xlsx(
            carpeta / "dos.xlsx",
            ["numero_factura", "fecha_radicacion"],
            [["HUS400", datetime(2026, 6, 20)]],
        )
        rad = rt.cargar_radicaciones_fuentes([], [carpeta])
        assert rad == {"HUS300": date(2026, 6, 10), "HUS400": date(2026, 6, 20)}
