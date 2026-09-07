"""El párrafo del tope contractual lo arma el motor, no el modelo.

Pedido del auditor el 01-09-2026, tras tres corridas de la prueba 2 (CL4506 ·
HUS0000601892 · NUEVA EPS) con el mismo resultado ante «EL VALOR UNITARIO DEL
CLAVO SUPERA EL TOPE CONTRACTUAL»:

  • corrida 2 → silencio total,
  • corrida 3 → «EL VALOR FACTURADO SE AJUSTA A LA COMPLEJIDAD DEL PROCEDIMIENTO»,
  • corrida 4 → silencio otra vez.

Para el hospital las tres son lo mismo: esa parte del dinero se ratifica. Así
que el párrafo sale del prompt y se arma en Python con los datos de la malla.

Lo que este párrafo afirma es lo verificable —qué contrato rige, qué tarifa
resulta de él, y que un tope debe constar por escrito— y le exige la cláusula a
la entidad. NO afirma que el valor cobrado sea el correcto: eso depende del
tarifario y de la fecha del servicio, y el motor no siempre los tiene.
"""

import pytest

from app.services.glosa_service import (
    _objecion_de_dinero_sin_resolver,
    _parrafo_tarifario_determinista,
    _quitar_causal_del_servicio,
    _quitar_causal_propia_del_cuerpo,
)

GLOSA = (
    "CL4506 | HUS0000601892 | NUEVA E.P.S. S.A. - SUBSIDIADO\n"
    "NO SE JUSTIFICA LA PERTINENCIA DEL MATERIAL DE OSTEOSINTESIS.\n"
    "ADICIONALMENTE EL VALOR UNITARIO DEL CLAVO SUPERA EL TOPE CONTRACTUAL."
)
FICHA_VENCIDA = {
    "numero": "CONTRATO CON VIGENCIA TERMINADA: 02-01-06-00077-2017 (venció 2026-03-31)",
    "tarifa": "TARIFA NO DETERMINADA — sin la fecha del servicio no se puede afirmar cuál rige.",
    "_vigencia_vencida": True,
}


class TestElParrafoTraeLosDatosDuros:
    def test_nombra_el_contrato_sin_repetir_la_advertencia(self):
        p = _parrafo_tarifario_determinista(GLOSA, FICHA_VENCIDA, "$ 7.310.000")
        assert "02-01-06-00077-2017" in p
        assert p.count("VIGENCIA TERMINADA") == 0, "la advertencia ya va en su recuadro"

    def test_exige_la_clausula_del_tope(self):
        p = _parrafo_tarifario_determinista(GLOSA, FICHA_VENCIDA, "")
        assert "NO IDENTIFICA LA CLÁUSULA" in p
        assert "NO ES OPONIBLE AL PRESTADOR" in p

    def test_cita_pacta_sunt_servanda_con_su_norma(self):
        p = _parrafo_tarifario_determinista(GLOSA, FICHA_VENCIDA, "")
        assert "PACTA SUNT SERVANDA" in p
        assert "ART. 1602" in p and "ART. 871" in p

    def test_pide_el_desglose_con_el_valor_objetado(self):
        p = _parrafo_tarifario_determinista(GLOSA, FICHA_VENCIDA, "$ 7.310.000")
        assert "$ 7.310.000" in p
        assert "DESGLOSE ARITMÉTICO" in p

    def test_sin_valor_objetado_no_inventa_una_cifra(self):
        p = _parrafo_tarifario_determinista(GLOSA, FICHA_VENCIDA, "")
        assert "DESGLOSE ARITMÉTICO" not in p

    def test_no_afirma_que_el_valor_cobrado_sea_correcto(self):
        """El motor no tiene el tarifario ni la fecha: no puede prometerlo."""
        p = _parrafo_tarifario_determinista(GLOSA, FICHA_VENCIDA, "$ 7.310.000").upper()
        for prometido in ("SE AJUSTA A LA COMPLEJIDAD", "EL VALOR ES CORRECTO", "ES RAZONABLE"):
            assert prometido not in p


class TestCadaSituacionContractualTieneSuTexto:
    def test_sin_contrato_va_soat_pleno_sin_descuentos(self):
        p = _parrafo_tarifario_determinista(
            GLOSA, {"numero": "SIN CONTRATO PACTADO", "tarifa": "SOAT PLENO"}, ""
        )
        assert "NO EXISTE ACUERDO DE VOLUNTADES" in p
        assert "SIN DESCUENTO ALGUNO" in p

    def test_contrato_vigente_nombra_la_tarifa_pactada(self):
        p = _parrafo_tarifario_determinista(
            GLOSA, {"numero": "C00060340", "tarifa": "SOAT -15%"}, ""
        )
        assert "SE RIGEN POR EL CONTRATO C00060340" in p
        assert "TARIFA PACTADA ES SOAT -15%" in p

    def test_ficha_vacia_no_rompe(self):
        assert _parrafo_tarifario_determinista(GLOSA, None, "").startswith("EN CUANTO A")
        assert _parrafo_tarifario_determinista(GLOSA, {}, "")


class TestSoloCuandoHaceFalta:
    def test_glosa_sin_objecion_de_plata_no_recibe_parrafo(self):
        assert _parrafo_tarifario_determinista("SO0102 NO SE ANEXA LA EPICRISIS.", {}, "") == ""

    def test_glosa_vacia_no_rompe(self):
        assert _parrafo_tarifario_determinista("", FICHA_VENCIDA, "") == ""

    def test_detecta_el_silencio_de_la_corrida_2_y_4(self):
        assert _objecion_de_dinero_sin_resolver(GLOSA, "ESE HUS NO ACEPTA... AUTONOMÍA MÉDICA.")

    def test_detecta_el_adjetivo_de_la_corrida_3(self):
        assert _objecion_de_dinero_sin_resolver(
            GLOSA, "EL VALOR FACTURADO SE AJUSTA A LA COMPLEJIDAD DEL PROCEDIMIENTO."
        )

    def test_respeta_a_la_ia_cuando_si_la_resolvio(self):
        assert not _objecion_de_dinero_sin_resolver(
            GLOSA, "SE EXIGE LA CLÁUSULA DEL TOPE INVOCADO; PACTA SUNT SERVANDA."
        )

    def test_respeta_a_la_ia_cuando_cita_el_contrato(self):
        assert not _objecion_de_dinero_sin_resolver(
            GLOSA, "LAS ATENCIONES SE RIGEN POR EL CONTRATO 02-01-06-00077-2017."
        )


class TestElSeparadorHuerfano:
    """Corrida 4: «OSTEOSÍNTESIS DE FÉMUR – código CL4506»."""

    @pytest.mark.parametrize("sep", ["–", "—", "-", ",", ";", ""])
    def test_lo_quita_venga_con_el_separador_que_venga(self, sep: str):
        t = f"OSTEOSÍNTESIS DE FÉMUR {sep} código CL4506".replace("  ", " ")
        assert _quitar_causal_del_servicio(t, "CL4506") == "OSTEOSÍNTESIS DE FÉMUR"

    def test_no_deja_el_guion_colgando_en_el_cuerpo(self):
        t = "EL PROCEDIMIENTO OSTEOSÍNTESIS DE FÉMUR – código CL4506 FUE PERTINENTE."
        r = _quitar_causal_propia_del_cuerpo(t, "CL4506")
        assert r == "EL PROCEDIMIENTO OSTEOSÍNTESIS DE FÉMUR FUE PERTINENTE."

    def test_un_cups_real_conserva_su_separador(self):
        t = "HEMOGRAMA IV – código 902210"
        assert _quitar_causal_del_servicio(t, "CL4506") == t
