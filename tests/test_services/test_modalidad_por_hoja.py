"""De qué manera quedó pactada cada tarifa.

OT-036 · 13-08-2026. Con el contrato de FAMISANAR ya firmado se pueden
cargar las 6.655 tarifas como pactadas. Antes de cargarlas apareció esto:
cualquier fila que no trajera una columna diciendo la modalidad entraba como
**«TARIFA PROPIA»**, por defecto.

En la propuesta 2026 eso alcanzaba a las **4.586 tarifas de la hoja UVB**,
que no son tarifas propias: son la UVB por grupos con el descuento del
contrato. El dictamen habría citado una forma de pactar distinta a la del
contrato, y eso lo lee la entidad — le da un argumento para ratificar la
glosa sin siquiera discutir el valor.

La corrección es del lector, no del dictamen: cuando la fila no dice nada,
la modalidad sale del nombre de la hoja de donde salió la tarifa. Si la hoja
sí trae su columna (ESPECIALIDAD, MODALIDAD…), esa manda y nada cambia.
"""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from app.services.tarifas_excel_parser import _modalidad_de_hoja, parsear_excel_tarifas


def _excel(nombre_hoja: str, headers: list[str], filas: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = nombre_hoja
    ws.append(headers)
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestLaModalidadSaleDeLaHoja:
    def test_la_uvb_no_es_una_tarifa_propia(self):
        assert _modalidad_de_hoja("UVB") == "UVB POR GRUPOS"

    @pytest.mark.parametrize(
        "hoja,esperado",
        [
            ("TARIFAS PROPIAS ", "TARIFA PROPIA"),
            ("PAQUETES", "PAQUETE"),
            ("AMBULATORIO", "AMBULATORIO"),
            ("ORTESIS Y PROTESIS", "ORTESIS Y PROTESIS"),
        ],
    )
    def test_las_demas_hojas_de_la_propuesta(self, hoja, esperado):
        assert _modalidad_de_hoja(hoja) == esperado

    def test_una_hoja_desconocida_se_nombra_tal_cual(self):
        """Vale más decir de qué hoja salió que inventarle una modalidad."""
        assert _modalidad_de_hoja("ANEXO RARO 7") == "ANEXO RARO 7"

    def test_sin_nombre_de_hoja_se_conserva_lo_de_antes(self):
        """Otros formatos ya cargados no pueden cambiar de comportamiento."""
        assert _modalidad_de_hoja("") == "TARIFA PROPIA"


class TestSobreElArchivoCompleto:
    def test_la_uvb_entra_como_uvb_y_no_como_propia(self):
        datos = _excel(
            "UVB",
            [
                "CUPS",
                "DESCRIPCION CUPS",
                "VALOR UVB 2026",
                "GRUPO / FACTOR",
                "TIPO",
                "PROPUESTA FINAL",
            ],
            [["010101", "PUNCION CISTERNAL VIA LATERAL", 880800, 4, "GRUPOS", 836800]],
        )
        filas = parsear_excel_tarifas(datos, "propuesta.xlsx")["filas"]
        assert len(filas) == 1
        assert filas[0]["modalidad"] == "UVB POR GRUPOS"
        assert filas[0]["modalidad"] != "TARIFA PROPIA"

    def test_se_sigue_cargando_el_valor_pactado_y_no_el_de_referencia(self):
        """El valor que se pacta es PROPUESTA FINAL. Si gana VALOR UVB 2026,
        el motor defiende con una tarifa 5% más alta que la pactada y la
        entidad ratifica la glosa cada vez (OT-014)."""
        datos = _excel(
            "UVB",
            [
                "CUPS",
                "DESCRIPCION CUPS",
                "VALOR UVB 2026",
                "GRUPO / FACTOR",
                "TIPO",
                "PROPUESTA FINAL",
            ],
            [["010101", "PUNCION CISTERNAL VIA LATERAL", 880800, 4, "GRUPOS", 836800]],
        )
        filas = parsear_excel_tarifas(datos, "propuesta.xlsx")["filas"]
        assert filas[0]["valor_pactado"] == 836800.0

    def test_la_columna_de_la_hoja_le_gana_al_nombre_de_la_hoja(self):
        """Si la hoja dice la especialidad, esa es la modalidad real."""
        datos = _excel(
            "PAQUETES",
            ["CUPS", "DESCRIPCION", "ESPECIALIDAD", "VALOR PACTADO"],
            [["881234", "PAQUETE DE UROLOGIA", "UROLOGIA", 1500000]],
        )
        filas = parsear_excel_tarifas(datos, "propuesta.xlsx")["filas"]
        assert filas[0]["modalidad"] == "UROLOGIA"

    def test_la_hoja_de_tarifas_propias_no_cambia(self):
        datos = _excel(
            "TARIFAS PROPIAS ",
            ["CUPS", "DESCRIPCION CUPS", "CODIGO IPS", "VALOR PACTADO"],
            [["013205", "SECCION DEL CUERPO CALLOSO", "013205H", 9647400]],
        )
        filas = parsear_excel_tarifas(datos, "propuesta.xlsx")["filas"]
        assert filas[0]["modalidad"] == "TARIFA PROPIA"
        assert filas[0]["codigo_ips"] == "013205H"
