"""El dictamen no puede negar el contrato que el motor sí encontró
(21-08-2026).

Yesid analizó `TA5801 - mayor valor cobrado en cesarea - 740001 CESAREA - valor
1980300` y en la MISMA pantalla salieron estas dos cosas:

    Arriba, calculado por el motor:
        «Tarifa pactada encontrada en el contrato · Defender 100%»
        CUPS 740001 · Contrato S-13-1-03-1-04958 · $2.072.200

    Y en el cuerpo del dictamen:
        «EN AUSENCIA DE CONTRATO BILATERAL FORMAL ENTRE EL HUS Y FAMISANAR
         EPS, EL VALOR TIENE FUNDAMENTO EN EL ARTÍCULO 87 DEL DECRETO 2423…»

Ante la EPS eso es regalarle el argumento: si el hospital dice que no hay
contrato, no puede después exigir que se respete la tarifa pactada.

LA CAUSA: la plantilla TA-G01 del banco trae escrita esa frase, y se le ofrecía
a la IA como ejemplo a imitar sin mirar si el motor ya había encontrado
contrato.

LO QUE **NO** SE HACE: borrar la plantilla. Cuando de verdad no hay contrato,
esa argumentación del Decreto 2423 Art. 87 es correcta y es la única defensa
que existe. Solo se deja de ofrecer cuando sí lo hay.
"""

from __future__ import annotations

import pytest

from app.services.glosa_service import _NIEGA_EL_CONTRATO, _hay_contrato_verificado

TA_G01 = (
    "ESE HUS NO ACEPTA GLOSA POR CONCEPTO DE PRESUNTO MAYOR VALOR COBRADO SOBRE ÍTEM "
    "LIQUIDADO CON TARIFA PROPIA INSTITUCIONAL. EN AUSENCIA DE CONTRATO BILATERAL FORMAL "
    "ENTRE EL HUS Y LA ENTIDAD PAGADORA, EL VALOR FACTURADO TIENE FUNDAMENTO LEGAL DIRECTO "
    "EN EL ARTÍCULO 87 DEL DECRETO 2423 DE 1996."
)

CON_CONTRATO = (
    "ESE HUS NO ACEPTA LA GLOSA. CONFORME AL CONTRATO S-13-1-03-1-04958 LA TARIFA PACTADA "
    "ES SOAT UVB VIGENTE MENOS CINCO POR CIENTO, Y EL VALOR FACTURADO SE AJUSTA A ELLA."
)


class TestSeReconoceLaFraseQueNiega:
    @pytest.mark.parametrize(
        "texto",
        [
            TA_G01,
            "SIN CONTRATO PACTADO SE APLICA LA TARIFA SOAT PLENO",
            "SIN CONTRATO VIGENTE ENTRE LAS PARTES",
            "NO EXISTE CONTRATO ENTRE EL HUS Y LA EPS",
            "no hay contrato suscrito para esta vigencia",
        ],
    )
    def test_se_marca(self, texto):
        assert _NIEGA_EL_CONTRATO.search(texto)

    @pytest.mark.parametrize(
        "texto",
        [
            CON_CONTRATO,
            "EL CONTRATO 440-DIGSA/DMBUG-2025 ESTUVO VIGENTE HASTA EL 30/07/2026",
            "SE ANEXA COPIA DEL CONTRATO SUSCRITO ENTRE LAS PARTES",
            "LA CLÁUSULA SEXTA DEL CONTRATO ESTABLECE LAS TARIFAS",
        ],
    )
    def test_no_se_marca_lo_que_afirma_el_contrato(self, texto):
        assert not _NIEGA_EL_CONTRATO.search(texto)


class TestCuandoSeConsideraQueHayContrato:
    def test_con_tarifa_pactada_si(self):
        """El caso de Yesid: contrato S-13-1-03-1-04958 con $2.072.200."""
        assert _hay_contrato_verificado(
            {"tarifa": {"valor_pactado": 2072200}, "valor_pactado_calc": 2072200}
        )

    def test_un_contrato_sin_tarifa_para_ese_cups_no_cuenta(self):
        """Si hay contrato pero no tarifa para ese CUPS, no se puede sostener
        «respétese lo pactado»: la defensa del Decreto 2423 sigue siendo la
        buena y no hay que apartarla."""
        assert not _hay_contrato_verificado({"tarifa": {}, "valor_pactado_calc": 0})

    def test_tarifa_en_cero_tampoco(self):
        assert not _hay_contrato_verificado(
            {"tarifa": {"valor_pactado": 0}, "valor_pactado_calc": 0}
        )

    def test_sin_informacion_no(self):
        assert not _hay_contrato_verificado(None)
        assert not _hay_contrato_verificado({})

    def test_un_valor_corrupto_no_revienta(self):
        assert not _hay_contrato_verificado(
            {"tarifa": {"valor_pactado": "no es un número"}, "valor_pactado_calc": None}
        )


class TestElFiltroEstaCableado:
    def test_se_aplica_antes_de_armar_los_ejemplos(self):
        """Si el filtro quedara DESPUÉS de inyectar los few-shots, no serviría
        de nada."""
        import inspect

        from app.services import glosa_service as mod

        fuente = inspect.getsource(mod)
        i_filtro = fuente.index("_hay_contrato_verificado(info_tarifa)")
        i_inyecta = fuente.index("EJEMPLOS DE RESPUESTAS GANADORAS PREVIAS")
        assert i_filtro < i_inyecta

    def test_la_plantilla_no_se_borra_del_banco(self):
        """Solo se deja de OFRECER cuando hay contrato. El banco la conserva
        para las glosas donde de verdad no lo hay."""
        import json
        from pathlib import Path

        banco = Path(__file__).resolve().parents[2] / "data" / "plantillas_hus_base.json"
        if not banco.is_file():  # pragma: no cover
            pytest.skip("el banco de plantillas no está en este entorno")
        crudo = json.loads(banco.read_text(encoding="utf-8"))
        filas = crudo if isinstance(crudo, list) else crudo.get("plantillas", [])
        textos = " ".join(str(f.get("argumento", "")) for f in filas)
        assert "AUSENCIA DE CONTRATO" in textos, (
            "se borró la plantilla del Decreto 2423, que es la defensa correcta "
            "cuando de verdad no hay contrato"
        )
