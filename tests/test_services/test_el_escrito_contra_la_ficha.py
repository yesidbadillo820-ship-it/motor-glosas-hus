"""El dictamen no puede contradecir el contrato que el motor tiene cargado.

Caso 1 de la prueba del 08-09-2026, glosa TA0701 de COOSALUD. El motor TIENE
el contrato —«68001C00060340-24 · SOAT -15 %», vigente hasta 2027— y lo
imprime en el recuadro del propio dictamen. Y en el mismo documento, la
argumentación decía:

    «EL VALOR LIQUIDADO COINCIDE CON LA TARIFA SOAT PLENO […] COOSALUD NO HA
     APORTADO ELEMENTOS DE PRUEBA QUE DEMUESTREN LA EXISTENCIA DE UNA TARIFA
     PACTADA DISTINTA O INFERIOR.»

Sí existe, y la tiene el hospital. A la entidad le basta leer el recuadro de
nuestro propio dictamen para tumbar la respuesta sin discutir el fondo — y en
una glosa de TARIFA, eso es concederle justo lo que objetó.

La red que ya existía solo miraba el contrato VENCIDO; con uno vigente nadie
cruzaba el texto contra la ficha. El aviso de «plata que el motor no calculó»
sí vio algo, pero solo avisaba: el dictamen salió con el sello verde.
"""

from __future__ import annotations

import pytest

from app.services.glosa_service import (
    _bloqueos_para_radicar,
    _contradice_la_ficha_contractual,
    _hay_tarifa_pactada_de_verdad,
)

# La ficha real de COOSALUD, tal como la devuelve `get_contrato`.
COOSALUD = {
    "numero": "68001C00060340-24 / 68001S00060339-24",
    "tarifa": "SOAT -15 %",
    "factor": 0.85,
    "vigencia": "2024-05-01 — 2027-04-30",
}

# El párrafo del caso 1, palabra por palabra.
ARGUMENTO_DEL_CASO_1 = (
    "ESE HUS NO ACEPTA GLOSA TA0701 POR CONCEPTO DE DIFERENCIA TARIFARIA. EL "
    "CÁLCULO APLICADO CORRESPONDE EXACTAMENTE AL VALOR ESTABLECIDO EN EL MANUAL "
    "TARIFARIO SOAT Y EL VALOR LIQUIDADO COINCIDE CON LA TARIFA SOAT PLENO. "
    "COOSALUD NO HA APORTADO ELEMENTOS DE PRUEBA QUE DEMUESTREN LA EXISTENCIA DE "
    "UNA TARIFA PACTADA DISTINTA O INFERIOR. SE SOLICITA EL LEVANTAMIENTO."
)


class TestElCasoReal:
    def test_se_detectan_las_dos_contradicciones(self):
        h = _contradice_la_ficha_contractual(ARGUMENTO_DEL_CASO_1, COOSALUD)
        assert len(h) == 2, h

    def test_se_nombra_la_tarifa_pactada_de_verdad(self):
        """El gestor tiene que leer qué contradice a qué, no un «revise»."""
        h = " · ".join(_contradice_la_ficha_contractual(ARGUMENTO_DEL_CASO_1, COOSALUD))
        assert "SOAT PLENO" in h and "SOAT -15 %" in h

    def test_se_señala_la_exigencia_de_prueba(self):
        h = " · ".join(_contradice_la_ficha_contractual(ARGUMENTO_DEL_CASO_1, COOSALUD))
        assert "ya tiene" in h


class TestCadaContradiccionPorSeparado:
    def test_decir_soat_pleno_con_descuento_pactado(self):
        d = "LA FACTURACIÓN SE REALIZÓ BAJO TARIFA SOAT PLENA."
        assert _contradice_la_ficha_contractual(d, COOSALUD)

    @pytest.mark.parametrize(
        "frase",
        [
            "NO EXISTE CONTRATO PACTADO ENTRE LAS PARTES.",
            "SIN CONTRATO PACTADO, SE LIQUIDA POR EL MANUAL.",
            "NO MEDIA ACUERDO SUSCRITO CON LA ENTIDAD.",
        ],
    )
    def test_negar_el_contrato_que_si_existe(self, frase):
        h = _contradice_la_ficha_contractual(frase, COOSALUD)
        assert h and "68001C00060340-24" in h[0]

    @pytest.mark.parametrize(
        "frase",
        [
            "LA EPS NO HA APORTADO PRUEBA DE UNA TARIFA PACTADA DISTINTA.",
            "LA ENTIDAD NO HA ACREDITADO LA EXISTENCIA DE UNA TARIFA PACTADA INFERIOR.",
            "NO HA DEMOSTRADO QUE OBRE UNA TARIFA PACTADA MENOR.",
        ],
    )
    def test_exigirle_a_la_eps_probar_lo_que_ya_tenemos(self, frase):
        assert _contradice_la_ficha_contractual(frase, COOSALUD)


class TestCuandoNoHayNadaQueContradecir:
    """Las puertas son estrechas a propósito: un aviso que sale siempre es un
    aviso que el gestor aprende a ignorar."""

    def test_un_escrito_correcto_no_se_marca(self):
        d = (
            "EL VALOR FACTURADO CORRESPONDE A LA TARIFA PACTADA SOAT -15 % DEL "
            "CONTRATO 68001C00060340-24, VIGENTE A LA FECHA DE LA ATENCIÓN."
        )
        assert _contradice_la_ficha_contractual(d, COOSALUD) == []

    def test_sin_contrato_decir_soat_pleno_es_correcto(self):
        """Es justo lo que se aplica a falta de pacto."""
        ficha = {"numero": "SIN CONTRATO PACTADO", "tarifa": "SOAT PLENO", "factor": 1.0}
        assert _contradice_la_ficha_contractual(ARGUMENTO_DEL_CASO_1, ficha) == []

    def test_con_la_vigencia_terminada_tampoco_se_marca(self):
        """Ese caso ya lo cubre la red del contrato vencido, que corrige la ficha."""
        ficha = dict(COOSALUD, _vigencia_vencida=True)
        assert _contradice_la_ficha_contractual(ARGUMENTO_DEL_CASO_1, ficha) == []

    def test_con_la_tarifa_indeterminada_tampoco(self):
        ficha = dict(COOSALUD, _tarifa_indeterminada=True)
        assert _contradice_la_ficha_contractual(ARGUMENTO_DEL_CASO_1, ficha) == []

    def test_un_pacto_a_soat_pleno_no_contradice_decir_soat_pleno(self):
        ficha = {"numero": "CT-99", "tarifa": "SOAT PLENO", "factor": 1.0}
        assert _contradice_la_ficha_contractual(ARGUMENTO_DEL_CASO_1, ficha) == []

    @pytest.mark.parametrize("ficha", [None, {}, "", 0, {"numero": "", "tarifa": ""}])
    def test_sin_ficha_no_rompe(self, ficha):
        assert _contradice_la_ficha_contractual(ARGUMENTO_DEL_CASO_1, ficha) == []

    def test_argumento_vacio_no_rompe(self):
        assert _contradice_la_ficha_contractual("", COOSALUD) == []
        assert _contradice_la_ficha_contractual(None, COOSALUD) == []


class TestQueCuentaComoPactoDeVerdad:
    def test_el_descuento_por_el_factor(self):
        assert _hay_tarifa_pactada_de_verdad(COOSALUD) is True

    def test_el_descuento_escrito_en_la_tarifa(self):
        assert (
            _hay_tarifa_pactada_de_verdad({"numero": "CT-1", "tarifa": "SOAT -20%", "factor": None})
            is True
        )

    def test_un_factor_de_uno_no_es_descuento(self):
        assert (
            _hay_tarifa_pactada_de_verdad({"numero": "CT-1", "tarifa": "SOAT PLENO", "factor": 1.0})
            is False
        )

    def test_un_factor_ilegible_no_rompe(self):
        assert (
            _hay_tarifa_pactada_de_verdad(
                {"numero": "CT-1", "tarifa": "SOAT PLENO", "factor": "no es un número"}
            )
            is False
        )


class TestEstoBloquea:
    """El aviso de «plata que el motor no calculó» ya existía y solo avisaba:
    el caso 1 salió con el sello verde encima de la contradicción."""

    def test_la_marca_bloquea_el_dictamen(self):
        d = (
            "<h4>EL ESCRITO CONTRADICE LA TARIFA PACTADA QUE TIENE EL MOTOR</h4>"
            "<p>La argumentación dice «SOAT PLENO» y lo pactado es «SOAT -15 %».</p>"
        )
        motivos = _bloqueos_para_radicar(d)
        assert motivos, "tiene que bloquear, no solo avisar"
        assert "contrato" in motivos[0].lower()

    def test_un_dictamen_limpio_no_queda_bloqueado_por_esto(self):
        assert _bloqueos_para_radicar("SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA.") == []


class TestElAvisoEstaEnchufado:
    def test_el_analisis_lo_llama_y_bloquea(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_contradice_la_ficha_contractual(" in src
        i = src.index("_contradice_la_ficha_contractual(")
        bloque = src[max(0, i - 400) : i + 2200]
        assert "CONTRADICE LA TARIFA PACTADA QUE TIENE EL MOTOR" in bloque
        assert "_ficha_vig" in bloque, "se cruza contra la ficha del motor, no contra el texto"
        assert "CONTRADICE-FICHA" in bloque, "un fallo no puede tumbar el dictamen"
