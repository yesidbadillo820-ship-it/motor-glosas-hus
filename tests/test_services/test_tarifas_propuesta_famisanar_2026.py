"""El lector de tarifas se saltaba tres hojas de la propuesta 2026.

06-08-2026 · Yesid subió PROPUESTA_2026_BASE_FINAL_FAMISANAR.xlsx, con cinco
hojas. El lector reconoció dos (TARIFAS PROPIAS y PAQUETES) y descartó las
otras tres **en silencio**: se habrían perdido 5.038 tarifas y el motor
habría quedado defendiendo con un catálogo incompleto.

Tres causas distintas:

  · UVB (4.586) — el valor que se pacta viene en "PROPUESTA FINAL", que no
    estaba en la lista de columnas de plata conocidas. Y convive con "VALOR
    UVB 2026", que es el de referencia: el pactado es ese menos el 5% del
    contrato. Si gana el de referencia, el motor defiende con una tarifa 5%
    más alta que la pactada y la glosa se ratifica.
  · AMBULATORIO (413) — la columna del CUPS se titula con la resolución que
    los define ("Res 2706/25"), no con la palabra CUPS.
  · ORTESIS Y PROTESIS (39) — encabezado corto, con una sola de las palabras
    clave conocidas; hacían falta dos para reconocer la fila.
"""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from app.services.tarifas_excel_parser import parsear_excel_tarifas


def _excel(hojas: dict[str, list[list]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(title=nombre)
        for f in filas:
            ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


HOJA_UVB = [
    ["CUPS", "DESCRIPCION CUPS", "VALOR UVB 2026", "GRUPO / FACTOR", "TIPO", "PROPUESTA FINAL"],
    ["010101", "PUNCION CISTERNAL VIA LATERAL", 880800, 4, "GRUPOS", 836800],
    ["010201", "PUNCION ASPIRACION DE LIQUIDO", 1114800, 5, "GRUPOS", 1059100],
]
HOJA_AMBULATORIO = [
    ["Res 2706/25", "DESCRIPCION CUPS", "CODIGO IPS", "DESCRIPCIÓN IPS", "TARIFA 2026"],
    ["902210", "HEMOGRAMA IV", "902210AMB", "HEMOGRAMA IV", 19700],
    ["903895", "CREATININA EN SUERO", "903895AMB", "CREATININA EN SUERO", 17000],
]
HOJA_ORTESIS = [
    ["CUPS", "DESCRIPCIÓN", "CÓDIGO", "DESCRIPCIÓN", "TARIFA 2026"],
    ["AGMO102T", "SOCKET DESARTICULACION", "AGMO102T", "SOCKET DESARTICULACION", 2786700],
    ["AGMO103T", "SOCKET PROTESIS TRANSFEMORAL", "AGMO103T", "SOCKET PROTESIS", 2302300],
]


@pytest.fixture
def leido():
    def _leer(hojas):
        return parsear_excel_tarifas(_excel(hojas), filename="PROPUESTA_2026_FAMISANAR.xlsx")

    return _leer


class TestLaHojaUVB:
    def test_la_hoja_se_reconoce(self, leido):
        r = leido({"UVB": HOJA_UVB})
        assert not r["errores"]
        assert len(r["filas"]) == 2

    def test_manda_la_propuesta_final_no_el_valor_de_referencia(self, leido):
        """El pactado es el UVB del año menos el 5% del contrato. Cargar el
        de referencia dejaría al motor defendiendo 5% por encima."""
        r = leido({"UVB": HOJA_UVB})
        valores = {f["codigo_cups"]: f["valor_pactado"] for f in r["filas"]}
        assert valores["010101"] == 836800
        assert valores["010201"] == 1059100
        assert 880800 not in valores.values(), "se cargó el valor de referencia"

    def test_la_relacion_con_el_contrato_se_mantiene(self, leido):
        """836.800 / 880.800 = 0,95 — el «SOAT UVB vigente −5%» del contrato."""
        r = leido({"UVB": HOJA_UVB})
        v = {f["codigo_cups"]: f["valor_pactado"] for f in r["filas"]}
        assert round(v["010101"] / 880800, 2) == 0.95


class TestLaHojaAmbulatorio:
    def test_encuentra_el_cups_titulado_con_la_resolucion(self, leido):
        r = leido({"AMBULATORIO": HOJA_AMBULATORIO})
        cups = {f["codigo_cups"] for f in r["filas"]}
        assert cups == {"902210", "903895"}

    def test_conserva_el_codigo_propio_del_hospital(self, leido):
        """El código IPS es el que permite encontrar la tarifa cuando la
        entidad glosa con el código viejo."""
        r = leido({"AMBULATORIO": HOJA_AMBULATORIO})
        por_cups = {f["codigo_cups"]: f for f in r["filas"]}
        assert por_cups["902210"]["codigo_ips"] == "902210AMB"


class TestLaHojaOrtesisYProtesis:
    def test_un_encabezado_corto_ya_no_descarta_la_hoja(self, leido):
        r = leido({"ORTESIS Y PROTESIS": HOJA_ORTESIS})
        assert len(r["filas"]) == 2

    def test_los_codigos_del_hospital_entran(self, leido):
        r = leido({"ORTESIS Y PROTESIS": HOJA_ORTESIS})
        v = {f["codigo_cups"]: f["valor_pactado"] for f in r["filas"]}
        assert v["AGMO102T"] == 2786700


class TestLasCincoHojasJuntas:
    def test_ninguna_se_pierde_en_silencio(self, leido):
        hojas = {
            "TARIFAS PROPIAS": [
                ["CUPS", "DESCRIPCION CUPS", "CODIGO IPS", "DESCRIPCION IPS", "TARIFA 2026"],
                ["013205", "SECCION DEL CUERPO CALLOSO", "013205H", "SECCION", 9647400],
            ],
            "UVB": HOJA_UVB,
            "PAQUETES": [
                ["CUPS 2341/25", "DESCRIPCIÓN CUPS", "CODIGO IPS", "DESCRIPCIÓN", "VALOR 2026"],
                ["423301", "POLIPECTOMIA DE ESOFAGO", "423301H", "PAQUETE", 3533100],
            ],
            "AMBULATORIO": HOJA_AMBULATORIO,
            "ORTESIS Y PROTESIS": HOJA_ORTESIS,
        }
        r = leido(hojas)
        assert not r["errores"]
        assert len(r["hojas_detectadas"]) == 5, r["hojas_detectadas"]
        assert len(r["filas"]) == 8


class TestNoSeAflojoDeMas:
    def test_una_hoja_sin_columna_de_valor_se_sigue_descartando(self, leido):
        hojas = {
            "AGRUPADORES": [
                ["CODIGO", "DESCRIPCION", "GRUPO", "OBSERVACION"],
                ["A1", "AGRUPADOR UNO", "G1", "nada"],
            ]
        }
        assert leido(hojas)["filas"] == []

    def test_una_hoja_sin_codigos_se_sigue_descartando(self, leido):
        hojas = {
            "RESUMEN": [
                ["CONCEPTO", "DESCRIPCION", "OBSERVACION", "TARIFA 2026"],
                ["total general", "suma de todo", "ninguna", 100],
            ]
        }
        assert leido(hojas)["filas"] == []

    def test_una_fila_sin_cups_valido_no_entra(self, leido):
        hojas = {
            "ORTESIS Y PROTESIS": [
                ["CUPS", "DESCRIPCIÓN", "CÓDIGO", "DESCRIPCIÓN", "TARIFA 2026"],
                ["TOTAL", "suma", "", "", 999999],
                ["AGMO102T", "SOCKET", "AGMO102T", "SOCKET", 2786700],
            ]
        }
        r = leido(hojas)
        assert [f["codigo_cups"] for f in r["filas"]] == ["AGMO102T"]

    def test_una_fila_en_cero_no_entra(self, leido):
        hojas = {
            "AMBULATORIO": [
                ["Res 2706/25", "DESCRIPCION CUPS", "CODIGO IPS", "DESCRIPCIÓN IPS", "TARIFA 2026"],
                ["902210", "HEMOGRAMA IV", "902210AMB", "HEMOGRAMA IV", 0],
            ]
        }
        assert leido(hojas)["filas"] == []

    def test_si_hay_columna_cups_de_verdad_manda_esa(self, leido):
        """La columna titulada con la resolución solo se usa cuando NO hay
        una columna CUPS propiamente dicha."""
        hojas = {
            "MIXTA": [
                ["Res 2706/25", "CUPS", "DESCRIPCION CUPS", "CODIGO IPS", "TARIFA 2026"],
                ["999999", "902210", "HEMOGRAMA IV", "902210AMB", 19700],
            ]
        }
        r = leido(hojas)
        assert [f["codigo_cups"] for f in r["filas"]] == ["902210"]
