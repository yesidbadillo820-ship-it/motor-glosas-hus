"""Al ADRES no se le declara dos veces la misma plata — 19-08-2026.

El reporte del ADRES abre **un renglón por cada causal** del mismo ítem, y la
pantalla pide una decisión por renglón (así trabaja el gestor). El GLOSADO ya
sabía no contar dos veces —usa la marca `cuenta_valor`—; el ACEPTADO no.

Reproducido con el caso real: factura HUS311371, TAC DE CRÁNEO SIMPLE glosado
$700.000 con dos causales (3209 y 3106). Aceptando en las dos:

    KPI Valor glosado : $700.000
    KPI Aceptado      : $1.400.000   ← el doble
    Carta al ADRES    : «...ACEPTADA PARCIAL POR VALOR DE $1.400.000»

El arreglo **no** es copiar el filtro `cuenta_valor` al aceptado: si el gestor
objeta el renglón que cuenta y acepta el que no cuenta, el aceptado saldría
cero — otro dictamen falso, al revés. Se consolida por ítem con tope en lo
glosado.

En el paquete 31078 el reporte repite renglones en 27 de 81 facturas, y son
las de más plata.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from glosas_adres_por_factura import aceptado_sin_duplicar  # noqa: E402

# El TAC del caso real: un ítem, glosado $700.000, dos causales.
TAC = ("HUS311371", "879101", 700000.0)


class TestLaReglaDeConsolidacion:
    def test_aceptar_en_las_dos_causales_declara_el_item_una_vez(self):
        assert (
            aceptado_sin_duplicar([(TAC, 700000, 700000, True), (TAC, 700000, 700000, False)])
            == 700000
        )

    def test_repartir_la_aceptacion_entre_causales_suma(self):
        """300 en una causal y 400 en la otra son 700, no 400."""
        assert (
            aceptado_sin_duplicar([(TAC, 700000, 300000, True), (TAC, 700000, 400000, False)])
            == 700000
        )

    def test_aceptar_solo_en_el_renglon_que_no_cuenta_no_da_cero(self):
        """La trampa del arreglo fácil: filtrar por `cuenta_valor` daría $0."""
        assert (
            aceptado_sin_duplicar([(TAC, 700000, 0, True), (TAC, 700000, 700000, False)]) == 700000
        )

    def test_aceptacion_parcial_se_respeta(self):
        assert (
            aceptado_sin_duplicar([(TAC, 700000, 200000, True), (TAC, 700000, 0, False)]) == 200000
        )

    def test_dos_items_iguales_de_verdad_cuentan_los_dos(self):
        """Una factura puede traer el mismo medicamento cargado dos veces."""
        assert (
            aceptado_sin_duplicar([(TAC, 700000, 700000, True), (TAC, 700000, 700000, True)])
            == 1400000
        )

    def test_sin_aceptar_nada_da_cero(self):
        assert aceptado_sin_duplicar([(TAC, 700000, 0, True), (TAC, 700000, 0, False)]) == 0

    def test_items_distintos_no_se_mezclan(self):
        otro = ("HUS311371", "993101", 50000.0)
        assert (
            aceptado_sin_duplicar([(TAC, 700000, 700000, True), (otro, 50000, 50000, True)])
            == 750000
        )

    def test_sin_renglones_da_cero(self):
        assert aceptado_sin_duplicar([]) == 0


class TestLaCartaQueSeRadica:
    def _carta(self, aceptado_a: float, aceptado_b: float) -> str:
        from preauditar_glosas_adres import FilaMacro, armar_texto_respuesta

        def fila(causal: str, texto: str, aceptado: float) -> FilaMacro:
            return FilaMacro(
                factura="HUS311371",
                codigo="879101",
                descripcion="TAC DE CRANEO SIMPLE",
                valor_glosado=700000.0,
                codigo_numerico=causal,
                descripcion_glosa=texto,
                observacion="SE ACEPTA",
                cantidad_aceptada="1",
                valor_aceptado=aceptado,
                observacion_tecnico="",
            )

        return armar_texto_respuesta(
            [
                fila("3209", "Servicio no pertinente", aceptado_a),
                fila("3106", "Falta soporte de historia clinica", aceptado_b),
            ]
        )

    def test_el_encabezado_no_declara_el_doble(self):
        encabezado = self._carta(700000.0, 700000.0).split("\n")[0]
        assert "$700.000" in encabezado, encabezado
        assert "$1.400.000" not in encabezado

    def test_el_encabezado_respeta_la_aceptacion_parcial(self):
        encabezado = self._carta(200000.0, 0.0).split("\n")[0]
        assert "$200.000" in encabezado, encabezado
