"""Una cláusula del contrato se cita como está, o no se cita.

Caso real (10-09-2026, factura HUS0000541440). El dictamen citó la CLÁUSULA
SEGUNDA del contrato 440-DIGSA/DMBUG-2025 y salió radicado así:

    «…ES POR LA SUMA DE TRES MIL DOSCIENTOS TREINTA Y CINCO MILLONES
     CINCUENTA MIL PESOS MCTE (el valor objetado consignado en el
     expediente), VALOR QUE SE ENCUENTRA RESPALDADO CON EL CDP NO 58925 …
     POR CINCUENTA MIL PESOS M/CTE (el valor objetado consignado en el
     expediente)…»

Dos fallas encadenadas:

1. La red que borra cifras inventadas (`_neutralizar_valores_inventados`)
   no sabía que las cláusulas del contrato son legítimas: el motor mismo se
   las inyecta al prompt desde el contrato firmado. Como esas cifras no
   venían en la glosa, las tomó por inventadas y las pisó — dentro de una
   transcripción literal. Citar mal un contrato es peor que no citarlo: la
   entidad abre su propio contrato, ve que no dice eso, y el dictamen entero
   pierde el peso.

2. Aun cuando la cifra sí es inventada, meter la frase neutra dentro de un
   paréntesis no significa nada y delata el retoque. El paréntesis después
   de una suma en letras existe para repetirla en números; si el número no
   se sostiene, lo honesto es que el paréntesis desaparezca.
"""

import inspect

from app.services.glosa_service import _neutralizar_valores_inventados

CLAUSULA_REAL = (
    "CLÁUSULA SEGUNDA - VALOR: PARA EFECTOS LEGALES, FISCALES Y "
    "PRESUPUESTALES, EL VALOR DEL PRESENTE CONTRATO ES POR LA SUMA DE TRES "
    "MIL DOSCIENTOS TREINTA Y CINCO MILLONES CINCUENTA MIL PESOS MCTE "
    "($3.235.050.000), VALOR QUE SE ENCUENTRA RESPALDADO CON EL CDP NO 58925 "
    "DEL NUEVE (9) DE OCTUBRE DE 2025 POR CINCUENTA MIL PESOS M/CTE "
    "($50.000), Y TRES MIL DOSCIENTOS TREINTA Y CINCO MILLONES DE PESOS "
    "M/CTE ($3.235.000.000)."
)
DICTAMEN = "EN LOS TÉRMINOS DE " + CLAUSULA_REAL
GLOSA = "FA0701 - CUPS 224249-2 - IOBITRIDOL - Valor objetado: $ 103.000"
FRASE_NEUTRA = "el valor objetado consignado en el expediente"


class TestLaClausulaSeCitaComoEs:
    def test_las_cifras_del_contrato_sobreviven(self):
        salida = _neutralizar_valores_inventados(
            DICTAMEN,
            valor_raw_input="103000",
            texto_input_usuario=GLOSA,
            extras=("HUS0000541440", "", "440-DIGSA/DMBUG-2025", CLAUSULA_REAL),
        )
        assert "$3.235.050.000" in salida
        assert "$50.000" in salida
        assert "$3.235.000.000" in salida
        assert FRASE_NEUTRA not in salida

    def test_la_transcripcion_queda_identica(self):
        salida = _neutralizar_valores_inventados(
            DICTAMEN,
            valor_raw_input="103000",
            texto_input_usuario=GLOSA,
            extras=(CLAUSULA_REAL,),
        )
        assert CLAUSULA_REAL in salida

    def test_el_motor_le_pasa_la_clausula_a_la_red(self):
        """Si nadie mete `_texto_clausulas` en extras, el defecto vuelve."""
        from app.services import glosa_service

        fuente = inspect.getsource(glosa_service)
        assert "_texto_clausulas" in fuente
        assert 'c.get("texto_literal")' in fuente, (
            "la clave real de una cláusula es texto_literal — con otra clave "
            "el texto llega vacío y la red vuelve a pisar el contrato"
        )


class TestElParentesisNoSeQuedaCojo:
    def test_una_cifra_de_verdad_inventada_se_lleva_su_parentesis(self):
        inventado = (
            "EL SERVICIO FUE FACTURADO POR LA SUMA DE NOVECIENTOS CINCUENTA "
            "MIL PESOS ($950.000), SEGÚN CONSTA."
        )
        salida = _neutralizar_valores_inventados(
            inventado, valor_raw_input="103000", texto_input_usuario=GLOSA
        )
        assert "$950.000" not in salida
        assert FRASE_NEUTRA not in salida
        assert "NOVECIENTOS CINCUENTA MIL PESOS, SEGÚN CONSTA." in salida

    def test_tambien_con_corchetes(self):
        salida = _neutralizar_valores_inventados(
            "EL VALOR DE UN MILLÓN [$1.000.000] NO CONSTA.",
            valor_raw_input="103000",
            texto_input_usuario=GLOSA,
        )
        assert FRASE_NEUTRA not in salida
        assert "UN MILLÓN NO CONSTA." in salida

    def test_fuera_de_parentesis_la_frase_neutra_sigue_haciendo_su_trabajo(self):
        """Sin paréntesis, sustituir es lo correcto: la oración se sostiene."""
        salida = _neutralizar_valores_inventados(
            "EL SERVICIO FUE FACTURADO POR $950.000 SEGÚN LA IA.",
            valor_raw_input="103000",
            texto_input_usuario=GLOSA,
        )
        assert "$950.000" not in salida
        assert FRASE_NEUTRA in salida

    def test_no_deja_espacios_ni_comas_sueltas(self):
        salida = _neutralizar_valores_inventados(
            "LA SUMA DE UN MILLÓN ($1.000.000) , CON CARGO AL CDP.",
            valor_raw_input="103000",
            texto_input_usuario=GLOSA,
        )
        assert "  " not in salida
        assert " ," not in salida


class TestLoQueNoDebiaCambiar:
    def test_un_dictamen_sin_cifras_inventadas_no_se_toca(self):
        limpio = "SE OBJETA POR $ 103.000 CONFORME AL ARTÍCULO 56 DE LA LEY 1438 DE 2011."
        assert (
            _neutralizar_valores_inventados(
                limpio, valor_raw_input="103000", texto_input_usuario=GLOSA
            )
            == limpio
        )

    def test_la_uvb_del_manual_soat_sigue_siendo_legitima(self):
        con_uvb = "LA UVB 2026 EQUIVALE A $12.110 SEGÚN LA CIRCULAR 047 DE 2025."
        assert "$12.110" in _neutralizar_valores_inventados(
            con_uvb, valor_raw_input="103000", texto_input_usuario=GLOSA
        )

    def test_texto_vacio(self):
        assert _neutralizar_valores_inventados("") == ""
