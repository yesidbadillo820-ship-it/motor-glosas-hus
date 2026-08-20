"""Tests del consolidado entre la carpeta de detallados y la macro del paquete.

La pregunta que responde el bot es la del auditor: «¿son las mismas facturas de
un lado y del otro, y si no, cuáles faltan y cuánta plata son?».
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

openpyxl = pytest.importorskip("openpyxl")

import cruzar_detallados_con_macro as cx  # noqa: E402

from .test_descontar_aceptado_detallado import escribir_detallado  # noqa: E402

# La macro trae el título en la fila 1 y el encabezado en la 2.
ENCABEZADO = {
    cx.COL_RADICACION: "Número Radicación",
    cx.COL_FACTURA: "Número Factura",
    cx.COL_PAQUETE: "Número Paquete",
    cx.COL_VALOR_RECLAMADO: "Valor Reclamado",
    cx.COL_VALOR_GLOSADO: "Valor Glosado",
    cx.COL_DESC_GLOSA: "Descripción Glosa",
    cx.COL_OBSERVACION: "OBSERVACION",
    cx.COL_VALOR_ACEPTADO: "VALOR ACEPTADO",
}


def fila_macro(
    factura,
    *,
    radicado="14344788",
    paquete="31068",
    reclamado=0,
    glosado=0,
    aceptado=0,
    glosa="3106- Soporte de material ausente",
    observacion="SE OBJETA",
):
    return {
        cx.COL_RADICACION: radicado,
        cx.COL_FACTURA: factura,
        cx.COL_PAQUETE: paquete,
        cx.COL_VALOR_RECLAMADO: reclamado,
        cx.COL_VALOR_GLOSADO: glosado,
        cx.COL_DESC_GLOSA: glosa,
        cx.COL_OBSERVACION: observacion,
        cx.COL_VALOR_ACEPTADO: aceptado,
    }


def escribir_macro(ruta: Path, filas) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=21, value="-   CANTIDAD ACEPTADA  . POR VALOR $91.617.467")
    for col, texto in ENCABEZADO.items():
        ws.cell(row=2, column=col, value=texto)
    for i, f in enumerate(filas, start=3):
        for col, valor in f.items():
            ws.cell(row=i, column=col, value=valor)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


class TestLeerLaMacro:
    def test_agrupa_por_factura_y_suma(self, tmp_path):
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [
                fila_macro("HUS1", reclamado=100, glosado=80, aceptado=10),
                fila_macro("HUS1", reclamado=200, glosado=150, aceptado=20),
                fila_macro("HUS2", reclamado=50, glosado=50),
            ],
        )
        datos = cx.leer_macro(macro)
        assert set(datos) == {"1", "2"}
        assert datos["1"].filas == 2
        assert (datos["1"].valor_reclamado, datos["1"].valor_glosado) == (300, 230)
        assert datos["1"].valor_aceptado == 30

    def test_las_glosas_totales_no_cuentan_como_por_responder(self, tmp_path):
        """Las filas con «Descripción Glosa» vacía son el desglose de una
        reclamación glosada entera: no se responden una por una."""
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [
                fila_macro("HUS1", glosa="3106- Soporte ausente"),
                fila_macro("HUS1", glosa=""),
                fila_macro("HUS1", glosa=None),
            ],
        )
        dato = cx.leer_macro(macro)["1"]
        assert dato.filas == 3
        assert dato.glosas_por_responder == 1

    def test_cuenta_como_quedo_respondida(self, tmp_path):
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [
                fila_macro("HUS1", observacion="SE OBJETA"),
                fila_macro("HUS1", observacion="se objeta"),
                fila_macro("HUS1", observacion="SE ACEPTA"),
                fila_macro("HUS1", observacion=""),
            ],
        )
        obs = cx.leer_macro(macro)["1"].observaciones
        assert obs["SE OBJETA"] == 2 and obs["SE ACEPTA"] == 1 and obs["(vacía)"] == 1

    def test_ignora_las_filas_que_no_son_de_una_factura(self, tmp_path):
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [fila_macro("TOTAL GENERAL"), fila_macro(""), fila_macro("HUS400001")],
        )
        assert list(cx.leer_macro(macro)) == ["400001"]

    def test_filtra_por_paquete(self, tmp_path):
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [fila_macro("HUS1", paquete="31068"), fila_macro("HUS2", paquete="31078")],
        )
        assert list(cx.leer_macro(macro, paquete="31078")) == ["2"]
        assert len(cx.leer_macro(macro)) == 2


class TestLeerLaCarpeta:
    def test_toma_la_factura_de_adentro_del_archivo(self, tmp_path):
        """El nombre del archivo puede estar mal; lo que se radica es lo de
        adentro."""
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "como_sea.xlsx", "HUS352890")
        assert cx.leer_detallados(carpeta) == {"352890": "como_sea.xlsx"}

    def test_si_el_archivo_no_dice_la_factura_usa_el_nombre(self, tmp_path):
        carpeta = tmp_path / "in"
        carpeta.mkdir()
        wb = openpyxl.Workbook()
        wb.active["A1"] = "hoja sin factura"
        wb.save(carpeta / "HUS400002.xlsx")
        assert cx.leer_detallados(carpeta) == {"400002": "HUS400002.xlsx"}

    def test_un_excel_dañado_no_tumba_el_cruce(self, tmp_path):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS352890.xlsx", "HUS352890")
        (carpeta / "roto.xlsx").write_bytes(b"esto no es un excel")
        datos = cx.leer_detallados(carpeta)
        assert datos["352890"] == "HUS352890.xlsx"
        assert datos["ROTO"] == "roto.xlsx"  # se queda con el nombre, en mayúscula

    def test_ignora_los_temporales_de_excel(self, tmp_path):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS352890.xlsx", "HUS352890")
        (carpeta / "~$HUS352890.xlsx").write_bytes(b"temporal")
        assert len(cx.leer_detallados(carpeta)) == 1


class TestElCruce:
    def _estados(self, cruces):
        return {c.factura: c.estado for c in cruces}

    def test_todo_cuadra(self):
        det = {"1": "HUS1.xlsx", "2": "HUS2.xlsx"}
        mac = {"1": cx.FacturaMacro(factura="HUS1"), "2": cx.FacturaMacro(factura="HUS2")}
        estados = self._estados(cx.cruzar(det, mac))
        assert set(estados.values()) == {cx.ESTADO_COMPLETA}

    def test_una_factura_de_la_macro_sin_detallado(self):
        det = {"1": "HUS1.xlsx"}
        mac = {"1": cx.FacturaMacro(factura="HUS1"), "9": cx.FacturaMacro(factura="HUS9")}
        cruces = cx.cruzar(det, mac)
        assert self._estados(cruces)["HUS9"] == cx.ESTADO_SIN_DETALLADO
        motivo = next(c.motivo for c in cruces if c.factura == "HUS9")
        assert "no exportó el detallado" in motivo

    def test_un_detallado_que_no_esta_en_la_macro(self):
        det = {"1": "HUS1.xlsx", "7": "HUS7.xlsx"}
        mac = {"1": cx.FacturaMacro(factura="HUS1")}
        estados = self._estados(cx.cruzar(det, mac))
        assert estados["HUS7.xlsx"] == cx.ESTADO_SOBRA

    def test_los_ceros_de_relleno_no_separan_la_misma_factura(self):
        """El detallado dice HUS0000352890 y la macro HUS352890."""
        det = {cx.normalizar_factura("HUS0000352890"): "HUS0000352890.xlsx"}
        mac = {cx.normalizar_factura("HUS352890"): cx.FacturaMacro(factura="HUS352890")}
        assert [c.estado for c in cx.cruzar(det, mac)] == [cx.ESTADO_COMPLETA]

    def test_las_que_faltan_van_de_primeras(self):
        det = {"2": "HUS2.xlsx"}
        mac = {"1": cx.FacturaMacro(factura="HUS1"), "2": cx.FacturaMacro(factura="HUS2")}
        assert [c.factura for c in cx.cruzar(det, mac)][0] == "HUS1"


class TestElExcelDelConsolidado:
    def _armar(self, tmp_path):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS352890.xlsx", "HUS352890")
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [
                fila_macro("HUS352890", reclamado=142200, glosado=132800, aceptado=2400),
                fila_macro(
                    "HUS311371",
                    radicado="14345108",
                    reclamado=39722100,
                    glosado=39722100,
                    glosa="",
                    observacion="SE SUBSANA",
                ),
            ],
        )
        salida = tmp_path / "CONSOLIDADO.xlsx"
        assert (
            cx.main(
                [
                    "--detallados",
                    str(carpeta),
                    "--macro",
                    str(macro),
                    "--salida",
                    str(salida),
                ]
            )
            == 0
        )
        return salida

    def test_trae_las_tres_hojas(self, tmp_path):
        wb = openpyxl.load_workbook(self._armar(tmp_path))
        assert wb.sheetnames == ["RESUMEN", "FACTURAS", "SIN DETALLADO"]

    def test_el_resumen_dice_cuantas_hay_de_cada_lado(self, tmp_path):
        ws = openpyxl.load_workbook(self._armar(tmp_path))["RESUMEN"]
        datos = {fila[0]: fila[1] for fila in ws.iter_rows(values_only=True) if fila[0]}
        assert datos["Facturas en la macro"] == 2
        assert datos["Facturas con detallado en la carpeta"] == 1
        assert datos["Están en los dos lados"] == 1
        assert datos["En la macro pero SIN detallado"] == 1
        assert datos["Valor glosado de las que no tienen detallado"] == 39722100

    def test_la_hoja_de_las_que_faltan_trae_solo_esas(self, tmp_path):
        ws = openpyxl.load_workbook(self._armar(tmp_path))["SIN DETALLADO"]
        filas = [f for f in ws.iter_rows(min_row=2, values_only=True) if f[0]]
        assert len(filas) == 1
        assert filas[0][0] == "HUS311371"
        assert filas[0][1] == "14345108"  # el radicado, para pedir la impresión
        assert filas[0][5] == 39722100
        assert "SE SUBSANA" in filas[0][7]

    def test_la_hoja_de_facturas_las_trae_todas(self, tmp_path):
        ws = openpyxl.load_workbook(self._armar(tmp_path))["FACTURAS"]
        filas = [f for f in ws.iter_rows(min_row=2, values_only=True) if f[0]]
        assert {f[0] for f in filas} == {"HUS352890", "HUS311371"}
        con = next(f for f in filas if f[0] == "HUS352890")
        assert con[1] == cx.ESTADO_COMPLETA and con[2] == "HUS352890.xlsx"


class TestCLI:
    def test_avisa_si_la_carpeta_no_existe(self, tmp_path, caplog):
        macro = escribir_macro(tmp_path / "m.xlsx", [fila_macro("HUS1")])
        codigo = cx.main(
            [
                "--detallados",
                str(tmp_path / "no_existe"),
                "--macro",
                str(macro),
                "--salida",
                str(tmp_path / "o.xlsx"),
            ]
        )
        assert codigo == 1
        assert "No existe la carpeta" in caplog.text

    def test_avisa_si_la_macro_no_trae_facturas(self, tmp_path, caplog):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS352890.xlsx", "HUS352890")
        macro = escribir_macro(tmp_path / "m.xlsx", [])
        codigo = cx.main(
            [
                "--detallados",
                str(carpeta),
                "--macro",
                str(macro),
                "--salida",
                str(tmp_path / "o.xlsx"),
            ]
        )
        assert codigo == 1
        assert "no trae ninguna factura" in caplog.text

    def test_el_resumen_en_pantalla(self, tmp_path, capsys):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS352890.xlsx", "HUS352890")
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [
                fila_macro("HUS352890"),
                fila_macro("HUS311371", radicado="14345108", glosado=39722100),
            ],
        )
        assert (
            cx.main(
                [
                    "--detallados",
                    str(carpeta),
                    "--macro",
                    str(macro),
                    "--salida",
                    str(tmp_path / "o.xlsx"),
                ]
            )
            == 0
        )
        texto = capsys.readouterr().out
        assert "Facturas en la macro     : 2" in texto
        assert "Detallados en la carpeta : 1" in texto
        assert "SIN detallado          : 1  (glosado $39.722.100)" in texto
        assert "HUS311371" in texto and "14345108" in texto
