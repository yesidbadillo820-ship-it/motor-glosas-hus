"""Tests del parser para el formato TARIFARIO HUS DMBUG (Ronda 46).

Excel con estructura:
  Hoja SERVICIOS IPS: CODIGO IPS | DESCRIPCIÓN CUPS | CUPS 2641/25 | DESCRIPCIÓN CUPS | FACTOR | VALOR 2025
  Hoja AMBULATORIO:   CODIGO IPS | DESCRIPCIÓN IPS  | CUPS 2341/24 | DESCRIPCION CUPS | FACTOR | TARIFA 2025 | SERVICIO
  Hoja PAQUETES:      CODIGO IPS | DESCRIPCIÓN CUPS | CUPS 2341/   | DESCRIPCIÓN CUPS | FACTOR | VALOR 202   | ESPECIALIDAD

El bug era que "TARIFA 2025" y "VALOR 2025" no matchean con
match exacto contra "VALOR"/"TARIFA".
"""
from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.services.tarifas_excel_parser import (
    _indice_columna,
    _tipo_hoja,
    parsear_excel_tarifas,
)


class TestIndiceColumnaPrefijos:
    def test_valor_matchea_valor_con_anio(self):
        headers = ["CODIGO IPS", "DESCRIPCION", "CUPS", "FACTOR", "VALOR 2025"]
        idx = _indice_columna(headers, "VALOR")
        assert idx == 4

    def test_tarifa_matchea_tarifa_con_anio(self):
        headers = ["CODIGO IPS", "DESCRIPCION", "CUPS", "FACTOR", "TARIFA 2025", "SERVICIO"]
        idx = _indice_columna(headers, "TARIFA")
        assert idx == 4

    def test_cups_matchea_cups_con_version(self):
        headers = ["CODIGO IPS", "DESCRIPCIÓN IPS", "CUPS 2341/24", "DESCRIPCION CUPS", "FACTOR"]
        idx = _indice_columna(headers, "CUPS")
        assert idx == 2  # primer header que empieza con 'CUPS '

    def test_match_exacto_sigue_prevaleciendo(self):
        headers = ["VALOR", "VALOR 2025"]
        idx = _indice_columna(headers, "VALOR")
        assert idx == 0


class TestTipoHojaHUSFormats:
    def test_hoja_servicios_ips(self):
        """Estructura de hoja SERVICIOS IPS del TARIFARIO HUS."""
        headers = ["CODIGO IPS", "DESCRIPCIÓN CUPS", "CUPS 2641/25",
                   "DESCRIPCIÓN CUPS", "FACTOR", "VALOR 2025"]
        headers_norm = [h.upper().strip() for h in headers]
        tipo = _tipo_hoja(headers_norm)
        assert tipo == "SIMPLE_FIJO"

    def test_hoja_ambulatorio(self):
        """Estructura de hoja AMBULATORIO."""
        headers = ["CODIGO IPS", "DESCRIPCIÓN IPS", "CUPS 2341/24",
                   "DESCRIPCION CUPS", "FACTOR", "TARIFA 2025", "SERVICIO"]
        headers_norm = [h.upper().strip() for h in headers]
        tipo = _tipo_hoja(headers_norm)
        assert tipo == "SIMPLE_FIJO"

    def test_hoja_paquetes(self):
        """Estructura de hoja PAQUETES (con año truncado)."""
        headers = ["CODIGO IPS", "DESCRIPCIÓN CUPS", "CUPS 2341/",
                   "DESCRIPCIÓN CUPS", "FACTOR", "VALOR 2025", "ESPECIALIDAD"]
        headers_norm = [h.upper().strip() for h in headers]
        tipo = _tipo_hoja(headers_norm)
        assert tipo == "SIMPLE_FIJO"


def _crear_excel_hus(hoja_name: str, headers: list, filas: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = hoja_name
    ws.append(headers)
    for f in filas:
        ws.append(f)
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()


class TestIntegracionExcelHUS:
    def test_parse_hoja_servicios_ips_detecta_filas(self):
        """Caso real del usuario: TARIFARIO ESE HUS 2025 - DMBUG."""
        excel_bytes = _crear_excel_hus(
            "SERVICIOS IPS",
            headers=[
                "CODIGO IPS", "DESCRIPCIÓN CUPS", "CUPS 2641/25",
                "DESCRIPCIÓN CUPS", "FACTOR", "VALOR 2025",
            ],
            filas=[
                ["010101H", "PUNCION CISTERNAL - VIA LATERAL", "010101",
                 "PUNCION CISTERNAL, VIA LATERAL", "SOAT (SMLMV)", 777793],
                ["890348H", "CONSULTA DE CONTROL GENETICA", "890348",
                 "CONSULTA DE CONTROL O DE SEGUIMIENTO POR GENETICA", "SOAT (SMLMV)", 231556],
            ],
        )
        resultado = parsear_excel_tarifas(excel_bytes, filename="TARIFARIO_HUS.xlsx")
        assert len(resultado["hojas_detectadas"]) >= 1
        assert len(resultado["filas"]) >= 2
        # Debe haber extraído el CUPS oficial y el código IPS
        cups_encontrados = {f["codigo_cups"] for f in resultado["filas"]}
        assert "890348" in cups_encontrados
        assert "010101" in cups_encontrados
        # El código IPS (39147B-18 style) debe quedar separado
        fila_genetica = next(f for f in resultado["filas"] if f["codigo_cups"] == "890348")
        assert fila_genetica["codigo_ips"] == "890348H"
        assert fila_genetica["valor_pactado"] == 231556.0

    def test_parse_hoja_ambulatorio_con_tarifa_2025(self):
        excel_bytes = _crear_excel_hus(
            "AMBULATORIO",
            headers=[
                "CODIGO IPS", "DESCRIPCIÓN IPS", "CUPS 2341/24",
                "DESCRIPCION CUPS", "FACTOR", "TARIFA 2025", "SERVICIO",
            ],
            filas=[
                ["902210AMB", "HEMOGRAMA IV", "902210",
                 "HEMOGRAMA IV", 0.37, 17600, "LABORATORIO"],
                ["903895AMB", "CREATININA", "903895",
                 "CREATININA EN SUERO", 0.31, 15200, "LABORATORIO"],
            ],
        )
        resultado = parsear_excel_tarifas(excel_bytes, filename="AMBULATORIO.xlsx")
        assert len(resultado["hojas_detectadas"]) >= 1
        assert len(resultado["filas"]) >= 2
        cups = {f["codigo_cups"] for f in resultado["filas"]}
        assert "902210" in cups
        assert "903895" in cups

    def test_plano_simple_valor_sin_anio(self):
        """Formato plano: CUPS + DESCRIPCION CUPS + TIPO + VALOR
        (4 columnas mínimas para pasar el detector de header)."""
        excel_bytes = _crear_excel_hus(
            "PLANO",
            headers=["CUPS", "DESCRIPCION CUPS", "TIPO", "VALOR"],
            filas=[["890348", "GENETICA", "SOAT", 231556]],
        )
        resultado = parsear_excel_tarifas(excel_bytes, filename="plano.xlsx")
        assert len(resultado["filas"]) == 1

    def test_codigo_ips_se_guarda_separado_del_cups(self):
        """Si CODIGO IPS y CUPS 2641/25 son distintos, el codigo_ips se
        guarda en el campo indexado (no solo en observación)."""
        excel_bytes = _crear_excel_hus(
            "SERVICIOS IPS",
            headers=[
                "CODIGO IPS", "DESCRIPCIÓN CUPS", "CUPS 2641/25",
                "DESCRIPCIÓN CUPS", "FACTOR", "VALOR 2025",
            ],
            filas=[
                # Caso típico: código IPS con sufijo 'H', CUPS limpio
                ["39147B-18", "CONSULTA GENETICA MEDICA", "890348",
                 "CONSULTA GENETICA", "SOAT (SMLMV)", 231556],
            ],
        )
        resultado = parsear_excel_tarifas(excel_bytes, filename="HUS.xlsx")
        assert len(resultado["filas"]) == 1
        fila = resultado["filas"][0]
        assert fila["codigo_cups"] == "890348"
        assert fila["codigo_ips"] == "39147B-18"
        assert fila["valor_pactado"] == 231556.0
