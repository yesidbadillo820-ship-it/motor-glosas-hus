"""Cada causal responde por SU plata, no por el total de la glosa.

10-09-2026. Caso real: objeción N° 189801 de la factura HUS0000541440 del
Dispensario. OCHO renglones — siete de SO4201 (soportes) y uno de FA0701
(cantidades de medicamento):

    SO4201 .... $ 55.882.100   (7 renglones)
    FA0701 .... $    103.000   (1 renglón)
    TOTAL ..... $ 55.985.100

El dictamen salió con **los dos bloques diciendo $55.985.100**. Un bloque de
ciento tres mil pesos afirmando que contesta cincuenta y cinco millones. La
entidad lo lee como que el hospital no entendió qué le glosaron — y ese es de
los flancos que el propio Quality Gate enumera para tumbar sin entrar al fondo.

POR QUÉ FALLABA: el reparto se rendía apenas veía una cifra ANTES del primer
código, porque «huele a total global». En la objeción de verdad esa cifra es
el VALOR FACTURA del encabezado, y el reparto nunca llegaba a intentarse.

LO QUE LO HACE UN HECHO Y NO UNA SUPOSICIÓN: cuando el texto declara un TOTAL
OBJETADO, la suma de las causales tiene que dar exactamente eso. Si cuadra, la
atribución está comprobada contra el propio papel de la entidad. Si no cuadra,
no se reparte: mejor que cada bloque muestre el total conocido a que muestre
una cifra inventada.
"""

from __future__ import annotations

import pytest

from app.services.multi_codigo import valores_por_codigo

# La objeción real, resumida a lo que importa para el reparto.
OBJECION_189801 = """FACTURA: HUS0000541440 · VALOR FACTURA: $126.565.918

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6276 MICROGUÍA
VALOR OBJETADO: $6.390.700,00

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6456 CATÉTER INTRODUCTOR
VALOR OBJETADO: $8.099.200,00

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6476 COIL
VALOR OBJETADO: $6.898.700,00

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6476 COIL (2 unidades)
VALOR OBJETADO: $13.797.400,00

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6476 COIL
VALOR OBJETADO: $6.898.700,00

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6476 COIL
VALOR OBJETADO: $6.898.700,00

SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de precios
FMQ6476 COIL
VALOR OBJETADO: $6.898.700,00

FA0701 - Los cargos por Medicamentos presentan diferencias con las cantidades
224249-2 IOBITRIDOL
VALOR OBJETADO: $103.000,00

TOTAL OBJETADO: $55.985.100,00"""


class TestElCasoQueLoDestapo:
    def test_cada_causal_recibe_lo_suyo(self):
        r = valores_por_codigo(OBJECION_189801, ["SO4201", "FA0701"])
        assert r == {"SO4201": "$ 55.882.100", "FA0701": "$ 103.000"}

    def test_la_causal_chica_no_reclama_el_total(self):
        """Un bloque de $103.000 diciendo $55.985.100 delata que no se entendió."""
        r = valores_por_codigo(OBJECION_189801, ["SO4201", "FA0701"])
        assert r["FA0701"] != "$ 55.985.100"

    def test_el_valor_factura_del_encabezado_no_se_le_atribuye_a_nadie(self):
        """Antes, esa cifra hacía que el reparto se rindiera del todo."""
        r = valores_por_codigo(OBJECION_189801, ["SO4201", "FA0701"])
        assert "126.565.918" not in " ".join(r.values())

    def test_los_siete_renglones_de_so4201_se_suman(self):
        r = valores_por_codigo(OBJECION_189801, ["SO4201", "FA0701"])
        # 6.390.700 + 8.099.200 + 6.898.700 + 13.797.400 + 6.898.700 × 3
        assert r["SO4201"] == "$ 55.882.100"


class TestLaSumaTieneQueCuadrarConElPapel:
    """Lo que separa un reparto comprobado de uno adivinado."""

    def test_si_no_cuadra_no_se_reparte(self):
        texto = OBJECION_189801.replace(
            "TOTAL OBJETADO: $55.985.100,00", "TOTAL OBJETADO: $99.999.999,00"
        )
        assert valores_por_codigo(texto, ["SO4201", "FA0701"]) == {}, (
            "si la suma no da el total declarado, algo se leyó mal: no se puede repartir"
        )

    def test_un_peso_de_diferencia_no_invalida_el_reparto(self):
        """Los redondeos de la entidad no pueden tumbar un reparto correcto."""
        texto = OBJECION_189801.replace(
            "TOTAL OBJETADO: $55.985.100,00", "TOTAL OBJETADO: $55.985.101,00"
        )
        assert valores_por_codigo(texto, ["SO4201", "FA0701"]) != {}

    def test_cien_pesos_de_diferencia_si_lo_invalida(self):
        texto = OBJECION_189801.replace(
            "TOTAL OBJETADO: $55.985.100,00", "TOTAL OBJETADO: $55.985.200,00"
        )
        assert valores_por_codigo(texto, ["SO4201", "FA0701"]) == {}


class TestLoQueYaFuncionabaSigueIgual:
    """La regla estrecha de siempre, para textos sin total declarado."""

    def test_un_monto_por_codigo(self):
        texto = "TA2902 se objeta $150.000 y SO3401 se objeta $80.000"
        assert valores_por_codigo(texto, ["TA2902", "SO3401"]) == {
            "TA2902": "$ 150.000",
            "SO3401": "$ 80.000",
        }

    @pytest.mark.parametrize(
        "texto,codigos,por_que",
        [
            (
                "$500.000 en total. TA2902 $150.000 y SO3401 $80.000",
                ["TA2902", "SO3401"],
                "hay plata antes del primer código y no hay total declarado",
            ),
            (
                "TA2902 $150.000 más $20.000 y SO3401 $80.000",
                ["TA2902", "SO3401"],
                "a un código le tocan dos montos",
            ),
            (
                "TA2902 $150.000 y también hay un SO9999",
                ["TA2902", "SO3401"],
                "un código de la lista no aparece",
            ),
            (
                "TA2902 por tarifa y SO3401 por epicrisis, sin cifras",
                ["TA2902", "SO3401"],
                "no hay montos",
            ),
            (
                "TA2902 $80.000 y SO3401 $80.000",
                ["TA2902", "SO3401"],
                "montos repetidos: huele a un solo valor global",
            ),
        ],
    )
    def test_devuelve_vacio(self, texto, codigos, por_que):
        assert valores_por_codigo(texto, codigos) == {}, f"repartió cuando {por_que}"

    def test_con_un_solo_codigo_no_hay_nada_que_repartir(self):
        assert valores_por_codigo("TA2902 $150.000", ["TA2902"]) == {}

    def test_texto_vacio_no_rompe(self):
        assert valores_por_codigo("", ["TA2902", "SO3401"]) == {}
        assert valores_por_codigo("TA2902 $1", []) == {}
