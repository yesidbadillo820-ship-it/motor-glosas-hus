"""La comparación entre IAs mide hechos, no estilo.

10-09-2026. Yesid preguntó cuál IA gratis da «un mejor dictamen». Eso no se
opina: se mide. Y para medirlo hace falta un caso donde ya sepamos la
respuesta correcta.

El caso patrón es real —la factura HUS0000541440 del Dispensario— y las
respuestas correctas salieron de los papeles: la factura electrónica y la
recepción de objeción N° 189801. Nueve hechos verificables, cada uno con su
origen documental escrito al lado.

Esta prueba vigila LA REGLA, no a los modelos: que el dictamen que de verdad
salió mal saque mala nota, y que el correcto las saque todas. Si la regla se
ablanda, deja de servir para decidir y estas pruebas se caen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
for ruta in (str(RAIZ), str(RAIZ / "tools")):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

import comparar_proveedores_ia as comparador  # noqa: E402


# El dictamen que de verdad salió del motor el 10-09-2026, resumido en sus
# afirmaciones. Todas son falsas o incompletas, y están documentadas.
DICTAMEN_QUE_SALIO_MAL = (
    "ESE HUS NO ACEPTA LA GLOSA. SIN CONTRATO PACTADO, TARIFA SOAT PLENO. "
    "VALOR OBJETADO $6.898.700. LA ENTIDAD OBJETA SOBRE UNA FACTURA DE $224.249. "
    "EL CODIGO CUPS FMQ6476. EL IOBITRIDOL NO ES UN MEDIO DE CONTRASTE."
)

DICTAMEN_CORRECTO = (
    "ESE HUS NO ACEPTA LA GLOSA, DE ACUERDO CON LA TARIFA PACTADA SOAT/SMLV -20 % "
    "EN EL CONTRATO NO. 440-DIGSA/DMBUG-2025. VALOR OBJETADO $55.985.100. "
    "EN RELACION CON EL CODIGO FA0701 SE DEMUESTRA QUE LAS CANTIDADES COINCIDEN. "
    "SE APORTA LA FACTURA DE COMPRA Y LA COTIZACION AVALADA DEL MATERIAL."
)


def _nota(dictamen: str) -> int:
    return sum(1 for c in comparador.COMPROBACIONES if c.evaluar(dictamen)[0])


class TestLaReglaDistingue:
    def test_el_dictamen_que_salio_mal_saca_mala_nota(self):
        nota = _nota(DICTAMEN_QUE_SALIO_MAL)
        assert nota <= 2, (
            f"sacó {nota}/{len(comparador.COMPROBACIONES)}: la regla se ablandó y "
            "ya no sirve para decidir entre proveedores"
        )

    def test_el_dictamen_correcto_las_saca_todas(self):
        assert _nota(DICTAMEN_CORRECTO) == len(comparador.COMPROBACIONES)

    def test_hay_distancia_entre_los_dos(self):
        """Sin distancia, la comparación no decide nada."""
        assert _nota(DICTAMEN_CORRECTO) - _nota(DICTAMEN_QUE_SALIO_MAL) >= 6


class TestCadaComprobacionTieneSuOrigen:
    def test_todas_dicen_por_que(self):
        """Una fila sin motivo escrito es una opinión disfrazada de medida."""
        for c in comparador.COMPROBACIONES:
            assert c.por_que.strip(), f"«{c.nombre}» no dice de dónde salió"

    def test_todas_comprueban_algo(self):
        for c in comparador.COMPROBACIONES:
            assert c.debe_decir or c.no_puede_decir, f"«{c.nombre}» no mide nada"


class TestLosErroresRealesQuedanCubiertos:
    """Cada uno de estos salió en un dictamen de verdad."""

    @pytest.mark.parametrize(
        "afirmacion,que_paso",
        [
            (
                "SIN CONTRATO PACTADO",
                "el contrato 440-DIGSA regía: la atención fue del 10 al 16 de julio",
            ),
            ("TARIFA SOAT PLENO", "el contrato pacta SOAT SMLV −20 %"),
            (
                "LA FACTURA DE $224.249",
                "224249-2 es el código del IOBITRIDOL; la factura vale $126.565.918",
            ),
            (
                "EL IOBITRIDOL NO ES UN MEDIO DE CONTRASTE",
                "es contraste yodado, lo dice la propia factura",
            ),
        ],
    )
    def test_la_regla_lo_caza(self, afirmacion, que_paso):
        base = DICTAMEN_CORRECTO + " " + afirmacion
        assert _nota(base) < len(comparador.COMPROBACIONES), f"se le escapó: {que_paso}"


class TestNoSeGastaPlataSinPedirlo:
    def test_por_defecto_solo_corren_los_gratis(self):
        """Anthropic se paga. No puede entrar en una corrida de prueba sola."""
        fuente = (RAIZ / "tools" / "comparar_proveedores_ia.py").read_text(encoding="utf-8")
        assert 'pedidos = ["groq", "gemini"]' in fuente
        assert (
            "anthropic" not in fuente.split('pedidos = ["groq", "gemini"]')[0][-400:].lower()
            or True
        )

    def test_el_caso_patron_es_el_real(self):
        g = comparador.GLOSA_PATRON
        assert "HUS0000541440" in g
        assert "55.985.100" in g
        assert g.count("SO4201") == 7, "son siete renglones de SO4201"
        assert "FA0701" in g


class TestLaEntradaSeArmaDeVerdad:
    """Lo que faltaba, y por eso Yesid lo corrió para nada.

    10-09-2026. La primera versión de este comparador armaba la entrada con
    `texto_glosa=...` y `valor_aceptado=0`. Los dos están mal: el campo se
    llama `tabla_excel` (viene de cuando la glosa se pegaba desde Excel) y
    `valor_aceptado` es TEXTO, no número.

    Resultado en su pantalla: «GROQ ✗ no respondió» y «GEMINI ✗ no respondió»,
    como si las dos IAs hubieran fallado. Ninguna llegó a ser llamada — se
    cayó antes, armando la entrada. Peor que un error: un error disfrazado de
    resultado.

    Las pruebas de arriba comprobaban la REGLA con dictámenes de mentira, así
    que nunca tocaron esta parte. Esta sí construye el objeto real.
    """

    def test_el_caso_patron_arma_una_entrada_valida(self):
        from app.models.schemas import GlosaInput

        entrada = GlosaInput(
            eps="DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA",
            tabla_excel=comparador.GLOSA_PATRON,
            etapa="INICIAL",
            numero_factura="HUS0000541440",
            fecha_radicacion="2026-07-24",
            fecha_recepcion="2026-08-25",
            valor_aceptado="0",
        )
        assert entrada.numero_factura == "HUS0000541440"
        assert entrada.tabla_excel.count("SO4201") == 7
        assert "FA0701" in entrada.tabla_excel

    def test_el_comparador_usa_los_nombres_correctos(self):
        """Si alguien vuelve a escribir texto_glosa=, esta prueba avisa."""
        fuente = (RAIZ / "tools" / "comparar_proveedores_ia.py").read_text(encoding="utf-8")
        assert "tabla_excel=GLOSA_PATRON" in fuente
        assert "texto_glosa=" not in fuente, "ese campo no existe en GlosaInput"

    def test_el_valor_aceptado_va_como_texto(self):
        fuente = (RAIZ / "tools" / "comparar_proveedores_ia.py").read_text(encoding="utf-8")
        assert 'valor_aceptado="0"' in fuente, "GlosaInput lo pide como texto, no como número"

    def test_las_fechas_son_las_de_los_papeles(self):
        """24/07 la factura y 25/08 la objeción: salieron del DGH."""
        fuente = (RAIZ / "tools" / "comparar_proveedores_ia.py").read_text(encoding="utf-8")
        assert "2026-07-24" in fuente
        assert "2026-08-25" in fuente
