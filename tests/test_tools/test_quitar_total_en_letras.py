"""Tests del bot que deja el detallado sin el total escrito en palabras.

Se reusa la geometría real del formato (cada dato dentro de un rango combinado)
del test del descontador: es la misma hoja que produce el sistema del hospital.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

openpyxl = pytest.importorskip("openpyxl")

import ajustar_detallado_glosas as aj  # noqa: E402
import quitar_total_en_letras as ql  # noqa: E402

from .test_descontar_aceptado_detallado import (  # noqa: E402
    TOT_ETIQUETA,
    TOT_VALOR,
    _poner,
    escribir_detallado,
)


def _celda_letras(ruta: Path):
    """(fila, columna, valor) de la celda del total en palabras."""
    ws = openpyxl.load_workbook(ruta)["Sheet"]
    for fila in ws.iter_rows():
        valores = [c for c in fila if c.value is not None]
        if valores and str(valores[0].value).strip().startswith("TOTAL:"):
            for c in valores[1:]:
                if isinstance(c.value, str):
                    return c.row, c.column, c.value
            return valores[0].row, None, None
    return None, None, None


class TestReconocerElImporteEnLetras:
    """No se vacía cualquier celda: solo la que trae un importe en palabras."""

    @pytest.mark.parametrize(
        "texto",
        [
            "CIENTO TREINTA MIL CUATROCIENTOS PESOS CON CERO CTVS M/Cte.",
            "CERO PESOS CON CERO CTVS M/Cte.",
            "SETENTA Y CUATRO MIL PESOS CON NOVENTA Y SIETE CTVS M/Cte.",
        ],
    )
    def test_lo_que_si_es(self, texto):
        assert ql.es_importe_en_letras(texto)

    @pytest.mark.parametrize(
        "texto",
        [
            "TOTAL:",
            "NOTAS FINALES:",
            "ELABORO",
            "VALOR TOTAL ORDEN DE SERVICIO",
            "PESOS COLOMBIANOS",  # dice PESOS pero no es un importe escrito
            "",
            None,
            130400,
        ],
    )
    def test_lo_que_no_es(self, texto):
        assert not ql.es_importe_en_letras(texto)


class TestUnaFactura:
    def test_deja_el_espacio_vacio(self, tmp_path):
        origen = tmp_path / "in"
        escribir_detallado(origen / "HUS352890.xlsx", "HUS352890")
        _, col_antes, texto_antes = _celda_letras(origen / "HUS352890.xlsx")
        assert "PESOS" in texto_antes

        salida = tmp_path / "out"
        res = ql.procesar([origen], salida)[0]
        assert res.estado == "LIMPIADO"
        assert res.borradas == [texto_antes]

        ruta = salida / "HUS352890.xlsx"
        ws = openpyxl.load_workbook(ruta)["Sheet"]
        fila, _, _ = _celda_letras(ruta)
        # La etiqueta TOTAL: sigue ahí y la celda de al lado quedó vacía.
        assert ws.cell(row=fila, column=6).value == "TOTAL:"
        assert ws.cell(row=fila, column=col_antes).value is None

    def test_los_numeros_no_se_tocan(self, tmp_path):
        origen = tmp_path / "in"
        escribir_detallado(origen / "HUS352890.xlsx", "HUS352890")
        salida = tmp_path / "out"
        ql.procesar([origen], salida)

        def totales(ruta):
            ws = openpyxl.load_workbook(ruta)["Sheet"]
            salida = {}
            for fila in ws.iter_rows():
                valores = [c.value for c in fila if c.value is not None]
                if valores and isinstance(valores[0], str):
                    salida[valores[0]] = valores[1:]
            return salida

        antes, despues = totales(origen / "HUS352890.xlsx"), totales(salida / "HUS352890.xlsx")
        assert despues[aj.MARCA_SUBTOTAL] == antes[aj.MARCA_SUBTOTAL]
        assert despues[aj.MARCA_TOTAL_ORDEN] == antes[aj.MARCA_TOTAL_ORDEN]
        assert despues["TOTAL:"] == []  # el renglón quedó sin nada al lado

    def test_no_toca_el_archivo_de_origen(self, tmp_path):
        origen = tmp_path / "in"
        escribir_detallado(origen / "HUS352890.xlsx", "HUS352890")
        antes = (origen / "HUS352890.xlsx").read_bytes()
        ql.procesar([origen], tmp_path / "out")
        assert (origen / "HUS352890.xlsx").read_bytes() == antes

    def test_los_servicios_quedan_intactos(self, tmp_path):
        origen = tmp_path / "in"
        escribir_detallado(origen / "HUS352890.xlsx", "HUS352890")
        salida = tmp_path / "out"
        ql.procesar([origen], salida)
        idx = aj.IndiceHoja(openpyxl.load_workbook(salida / "HUS352890.xlsx")["Sheet"])
        fac = aj.segmentar_facturas(idx)[0]
        items = [i for b in aj.leer_bloques(idx, aj.detectar_estructura(idx, fac)) for i in b.items]
        assert [(i.codigo, i.vr_ent) for i in items] == [
            ("39145", 85800.0),
            ("FMQ0046", 47000.0),
        ]

    def test_pasarlo_dos_veces_no_rompe_nada(self, tmp_path):
        origen = tmp_path / "in"
        escribir_detallado(origen / "HUS352890.xlsx", "HUS352890")
        una = tmp_path / "una"
        ql.procesar([origen], una)
        dos = tmp_path / "dos"
        res = ql.procesar([una], dos)[0]
        assert res.estado == "SIN_LETRAS"
        assert "No se encontró" in res.observacion


class TestCasosBorde:
    def test_una_hoja_con_varias_facturas_apiladas(self, tmp_path):
        """El formato del sistema apila facturas: hay que vaciarlas todas."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet"
        fila = 1
        for factura, valor in (("HUS1", 132800), ("HUS2", 95200)):
            _poner(ws, fila, (6, 26), aj.TITULO_NUEVO)
            _poner(ws, fila, (27, 49), factura)
            _poner(ws, fila + 2, TOT_ETIQUETA, aj.MARCA_TOTAL_ORDEN)
            _poner(ws, fila + 2, TOT_VALOR, float(valor))
            _poner(ws, fila + 3, (6, 10), "TOTAL:")
            _poner(ws, fila + 3, (11, 66), aj.numero_a_letras(valor))
            fila += 6
        origen = tmp_path / "in"
        origen.mkdir()
        wb.save(origen / "lote.xlsx")

        salida = tmp_path / "out"
        res = ql.procesar([origen], salida)[0]
        assert len(res.borradas) == 2
        ws2 = openpyxl.load_workbook(salida / "lote.xlsx")["Sheet"]
        textos = [str(c.value) for f in ws2.iter_rows() for c in f if c.value is not None]
        assert not any("PESOS" in t for t in textos)
        assert "TOTAL:" in textos  # las etiquetas siguen

    def test_no_borra_otro_texto_del_mismo_renglon(self, tmp_path):
        """En el renglón del TOTAL puede haber más cosas escritas. Solo se vacía
        el importe en palabras; lo demás se queda."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet"
        _poner(ws, 1, (6, 26), aj.TITULO_NUEVO)
        _poner(ws, 1, (27, 49), "HUS7")
        _poner(ws, 3, (6, 10), "TOTAL:")
        _poner(ws, 3, (11, 50), aj.numero_a_letras(1000))
        _poner(ws, 3, (51, 60), "SON PESOS COLOMBIANOS")
        origen = tmp_path / "in"
        origen.mkdir()
        wb.save(origen / "extra.xlsx")

        salida = tmp_path / "out"
        res = ql.procesar([origen], salida)[0]
        assert len(res.borradas) == 1
        ws2 = openpyxl.load_workbook(salida / "extra.xlsx")["Sheet"]
        assert ws2.cell(row=3, column=11).value is None
        assert ws2.cell(row=3, column=51).value == "SON PESOS COLOMBIANOS"

    def test_un_archivo_sin_ese_renglon_se_informa_y_se_copia(self, tmp_path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet"
        _poner(ws, 1, (6, 26), aj.TITULO_NUEVO)
        _poner(ws, 1, (27, 49), "HUS9")
        _poner(ws, 3, TOT_ETIQUETA, aj.MARCA_TOTAL_ORDEN)
        _poner(ws, 3, TOT_VALOR, 1000.0)
        origen = tmp_path / "in"
        origen.mkdir()
        wb.save(origen / "raro.xlsx")

        salida = tmp_path / "out"
        res = ql.procesar([origen], salida)[0]
        assert res.estado == "SIN_LETRAS"
        assert (salida / "raro.xlsx").exists()  # igual se entrega, sin tocar

    def test_un_excel_dañado_no_tumba_el_lote(self, tmp_path):
        origen = tmp_path / "in"
        escribir_detallado(origen / "HUS352890.xlsx", "HUS352890")
        (origen / "roto.xlsx").write_bytes(b"esto no es un excel")
        estados = {r.archivo: r.estado for r in ql.procesar([origen], tmp_path / "out")}
        assert estados["HUS352890.xlsx"] == "LIMPIADO"
        assert estados["roto.xlsx"] == "ERROR"

    def test_ignora_los_temporales_de_excel(self, tmp_path):
        origen = tmp_path / "in"
        escribir_detallado(origen / "HUS352890.xlsx", "HUS352890")
        (origen / "~$HUS352890.xlsx").write_bytes(b"temporal")
        assert len(ql.procesar([origen], tmp_path / "out")) == 1

    def test_carpeta_vacia_avisa(self, tmp_path):
        vacia = tmp_path / "vacia"
        vacia.mkdir()
        with pytest.raises(ValueError, match="No se encontró"):
            ql.procesar([vacia], tmp_path / "out")


class TestCLI:
    def test_corrida_completa_con_reporte(self, tmp_path, capsys):
        origen = tmp_path / "in"
        escribir_detallado(origen / "HUS352890.xlsx", "HUS352890")
        salida = tmp_path / "out"
        reporte = tmp_path / "r.csv"
        assert (
            ql.main(
                [
                    "--origen",
                    str(origen),
                    "--salida",
                    str(salida),
                    "--reporte-csv",
                    str(reporte),
                ]
            )
            == 0
        )
        assert "con el total en letras quitado : 1" in capsys.readouterr().out
        lineas = reporte.read_text(encoding="utf-8-sig").splitlines()
        assert lineas[0].startswith("ARCHIVO;ESTADO;CUANTOS")
        assert "LIMPIADO" in lineas[1] and "PESOS" in lineas[1]

    def test_dry_run_no_escribe(self, tmp_path):
        origen = tmp_path / "in"
        escribir_detallado(origen / "HUS352890.xlsx", "HUS352890")
        salida = tmp_path / "no_debe_existir"
        assert ql.main(["--origen", str(origen), "--salida", str(salida), "--dry-run"]) == 0
        assert not salida.exists()

    def test_carpeta_vacia_devuelve_error(self, tmp_path, caplog):
        vacia = tmp_path / "vacia"
        vacia.mkdir()
        assert ql.main(["--origen", str(vacia), "--salida", str(tmp_path / "o")]) == 1
        assert "No se encontró" in caplog.text
