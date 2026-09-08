"""Tests del organizador de objeciones de SANITAS
(tools/organizar_objeciones_sanitas.py).

Lo delicado de este archivo: SANITAS repite el encabezado «NUMERO DE FACTURA»
en la segunda columna, donde en realidad manda el CÓDIGO DE GLOSA. Por eso las
columnas se leen por posición y se verifica el contenido. Cubre: esa
verificación, la limpieza del código de glosa, el armado de las 16 columnas con
las reglas fijas (CTNCENCOS vacía, CROTIPOBJ por factura, SLNSERPRO sólo con
códigos que existan en el DGH) y el CLI de punta a punta.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

# El script vive en tools/ (sin __init__.py): lo importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import organizar_objeciones_sanitas as org  # noqa: E402

openpyxl = pytest.importorskip("openpyxl")

_FECHA = dt.datetime(2026, 9, 4)

# Los encabezados REALES del archivo de SANITAS, con la columna 2 mal rotulada.
_HEADERS = [
    "NUMERO DE FACTURA",
    "NUMERO DE FACTURA",
    "VALOR REAL GLOSA",
    "CODIGO PROCEDIMIENTO",
    "NOMBRE PROCEDIMIENTO",
    "CANTIDAD PROCEDIMIENTO",
    "OBSERVACIONES",
]

_HEADERS_DGH = [
    "SERVICIOS DGH",
    "DESCRIPCION INSTITUCIONAL",
    "SLNSERPRO_CUPS",
    "DESCRIPCION CUPS",
    "CODIGO_MEDICAMENTO",
    "FACTURA",
    "CAT_SERVICIOS",
    "Vr_SERVICIO",
    "SALDO_FACT",
]


def _crear_sanitas(ruta: Path, filas: list[list], headers: list[str] | None = None) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Glosa"
    ws.append(headers or _HEADERS)
    for f in filas:
        ws.append(f)
    wb.save(str(ruta))
    return ruta


def _crear_dgh(ruta: Path, filas: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(_HEADERS_DGH)
    for f in filas:
        ws.append(f)
    wb.save(str(ruta))
    return ruta


_FILAS = [
    ["HUS0000548650", "CO2301", 2350, "903883", "GLUCOMETRIA GLUCOSA SEMIAUTOMATIZADA", "1", "Glosa Calculada Afiliado"],
    ["HUS0000548650", "TA0801", 76400, "911302", "EXANGUINO TRANSFUSION O PLASMAFERESIS", "1", "TARIFA"],
]  # fmt: skip

_FILAS_DGH = [
    ["903883H", "GLUCOMETRIA GLUCOSA SEMIAUTOMATIZADA", "903883", "", "", "HUS0000548650", 1, 4700, 113421546],
    ["911302", "EXANGUINO TRANSFUSION O PLASMAFERESIS (D", "911302", "", "", "HUS0000548650", 1, 76400, 113421546],
]  # fmt: skip


# ─── Limpieza del código de glosa ────────────────────────────────────────────


class TestCodigoGlosa:
    def test_ya_viene_limpio(self):
        assert org.codigo_glosa("CO2301") == "CO2301"

    def test_partido_por_un_espacio(self):
        assert org.codigo_glosa("TA08 01") == "TA0801"

    def test_con_espacios_de_mas(self):
        assert org.codigo_glosa("  au5801 ") == "AU5801"

    def test_vacio(self):
        assert org.codigo_glosa(None) == ""


class TestCrotipobj:
    def test_los_tres_valores(self):
        assert org.crotipobj_factura({"CO", "TA"}) == 0  # administrativa
        assert org.crotipobj_factura({"CL"}) == 1  # médica
        assert org.crotipobj_factura({"CL", "CO"}) == 2  # mixta


# ─── La trampa del encabezado ────────────────────────────────────────────────


class TestVerificarColumnas:
    def test_archivo_correcto_pasa(self, tmp_path):
        ruta = _crear_sanitas(tmp_path / "s.xlsx", _FILAS)
        assert len(org.leer_sanitas(ruta)) == 2

    def test_columnas_en_otro_orden_se_detiene(self, tmp_path):
        """Si el código de glosa no está en la segunda columna, el bot para."""
        filas = [
            ["HUS0000548650", "903883", 2350, "CO2301", "GLUCOMETRIA", "1", "x"],
        ]
        ruta = _crear_sanitas(tmp_path / "s.xlsx", filas)
        with pytest.raises(ValueError, match="códigos de glosa"):
            org.leer_sanitas(ruta)

    def test_primera_columna_que_no_es_factura(self, tmp_path):
        filas = [["CO2301", "CO2301", 2350, "903883", "GLUCOMETRIA", "1", "x"]]
        ruta = _crear_sanitas(tmp_path / "s.xlsx", filas)
        with pytest.raises(ValueError, match="número de factura"):
            org.leer_sanitas(ruta)

    def test_archivo_sin_renglones(self, tmp_path):
        ruta = _crear_sanitas(tmp_path / "s.xlsx", [])
        with pytest.raises(ValueError, match="no tiene renglones"):
            org.leer_sanitas(ruta)


class TestLectura:
    def test_lee_cada_dato_de_su_columna(self, tmp_path):
        ruta = _crear_sanitas(tmp_path / "s.xlsx", _FILAS)
        objeciones = org.leer_sanitas(ruta)
        o = objeciones[0]
        assert o["cxc"] == "HUS0000548650"
        assert o["codigo"] == "CO2301"  # de la columna 2, no del procedimiento
        assert o["cod_servicio"] == "903883"
        assert o["servicio"].startswith("GLUCOMETRIA")
        assert o["valor"] == 2350
        assert o["cantidad"] == 1


# ─── Las 16 columnas y las reglas fijas ──────────────────────────────────────


class TestFilas:
    def _filas(self, tmp_path, servicios=True):
        entrada = _crear_sanitas(tmp_path / "s.xlsx", _FILAS)
        dgh = _crear_dgh(tmp_path / "d.xlsx", _FILAS_DGH)
        from _cruce_dgh import leer_servicios_dgh

        serv = leer_servicios_dgh(dgh) if servicios else None
        trazas: list[dict] = []
        return org.construir_filas(org.leer_sanitas(entrada), _FECHA, serv, trazas), trazas

    def test_slnserpro_sale_con_el_codigo_del_dgh(self, tmp_path):
        filas, _ = self._filas(tmp_path)
        # SANITAS manda 903883 y el DGH lo tiene como 903883H: gana el del DGH.
        assert filas[0]["SLNSERPRO"] == "903883H"
        assert filas[1]["SLNSERPRO"] == "911302"

    def test_ctncencos_siempre_vacia(self, tmp_path):
        filas, _ = self._filas(tmp_path)
        assert all(f["CTNCENCOS"] is None for f in filas)

    def test_crotipobj_por_factura(self, tmp_path):
        filas, _ = self._filas(tmp_path)
        assert all(f["CROTIPOBJ"] == 0 for f in filas)  # CO y TA: administrativas

    def test_crotipobj_mixta(self, tmp_path):
        filas = _FILAS + [
            ["HUS0000548650", "CL0801", 1000, "903883", "GLUCOMETRIA", "1", "x"],
        ]
        entrada = _crear_sanitas(tmp_path / "s.xlsx", filas)
        armadas = org.construir_filas(org.leer_sanitas(entrada), _FECHA)
        assert [f["CROTIPOBJ"] for f in armadas] == [2, 2, 2]

    def test_servicio_que_no_esta_en_la_factura_queda_vacio(self, tmp_path):
        filas = [["HUS0000548650", "CO2301", 999, "999999", "SERVICIO INEXISTENTE", "1", "x"]]
        entrada = _crear_sanitas(tmp_path / "s.xlsx", filas)
        dgh = _crear_dgh(tmp_path / "d.xlsx", _FILAS_DGH)
        from _cruce_dgh import leer_servicios_dgh

        trazas: list[dict] = []
        armadas = org.construir_filas(
            org.leer_sanitas(entrada), _FECHA, leer_servicios_dgh(dgh), trazas
        )
        assert armadas[0]["SLNSERPRO"] is None
        assert trazas[0]["confianza"] == "SIN CRUCE"

    def test_sin_export_del_dgh_no_escribe_codigos(self, tmp_path):
        filas, _ = self._filas(tmp_path, servicios=False)
        assert all(f["SLNSERPRO"] is None for f in filas)

    def test_constantes_y_consecutivo(self, tmp_path):
        filas, _ = self._filas(tmp_path)
        assert all(f["GENUSUARIO4"] == "999" and f["CROCLAOBJ"] == 0 for f in filas)
        assert all(f["CDCONSEC"] == "1" for f in filas)  # una sola factura
        assert all(f["CDFECDOC"] == _FECHA for f in filas)

    def test_crdobserv(self, tmp_path):
        filas, _ = self._filas(tmp_path)
        obs = filas[0]["CRDOBSERV"]
        assert obs.startswith("CO2301 GLUCOMETRIA")
        assert ": Glosa Calculada Afiliado" in obs
        assert obs.endswith("$2350")

    def test_consecutivo_por_factura(self, tmp_path):
        filas = _FILAS + [
            ["HUS0000549000", "CO2301", 500, "903883", "GLUCOMETRIA", "1", "x"],
        ]
        entrada = _crear_sanitas(tmp_path / "s.xlsx", filas)
        armadas = org.construir_filas(org.leer_sanitas(entrada), _FECHA)
        assert [f["CDCONSEC"] for f in armadas] == ["1", "1", "2"]


# ─── CLI ─────────────────────────────────────────────────────────────────────


class TestCli:
    def test_end_to_end(self, tmp_path):
        entrada = _crear_sanitas(tmp_path / "SANITAS.xlsx", _FILAS)
        dgh = _crear_dgh(tmp_path / "DGH.xlsx", _FILAS_DGH)
        salida = tmp_path / "OBJECIONES_SANITAS_04092026.xlsx"
        reporte = tmp_path / "CRUCE_SANITAS_04092026.xlsx"
        assert (
            org.main(
                [
                    "--entrada",
                    str(entrada),
                    "--servicios-dgh",
                    str(dgh),
                    "--salida",
                    str(salida),
                    "--consolidado",
                    "--reporte-cruce",
                    str(reporte),
                    "--fecha",
                    "2026-09-04",
                ]
            )
            == 0
        )
        ws = openpyxl.load_workbook(str(salida))["OBJECIONES"]
        assert [c.value for c in ws[1]] == list(org.COLUMNAS_OBJECIONES)
        fila = dict(zip([c.value for c in ws[1]], [c.value for c in ws[2]], strict=True))
        assert fila["CRNCXC"] == "HUS0000548650"
        assert fila["CRNCONOBJ"] == "CO2301"
        assert fila["SLNSERPRO"] == "903883H"
        assert fila["CTNCENCOS"] is None
        assert fila["CROTIPOBJ"] == 0
        wb2 = openpyxl.load_workbook(str(reporte))
        assert wb2.sheetnames == ["CRUCE", "REVISAR", "RESUMEN"]

    def test_un_archivo_por_factura(self, tmp_path):
        entrada = _crear_sanitas(tmp_path / "SANITAS.xlsx", _FILAS)
        destino = tmp_path / "salida"
        assert org.main(["--entrada", str(entrada), "--salida", str(destino)]) == 0
        assert (destino / "OBJECIONES_SANITAS_HUS0000548650.xlsx").is_file()

    def test_reporte_sin_export_del_dgh_avisa(self, tmp_path):
        entrada = _crear_sanitas(tmp_path / "SANITAS.xlsx", _FILAS)
        assert (
            org.main(
                [
                    "--entrada",
                    str(entrada),
                    "--salida",
                    str(tmp_path / "o.xlsx"),
                    "--consolidado",
                    "--reporte-cruce",
                    str(tmp_path / "c.xlsx"),
                ]
            )
            == 1
        )
