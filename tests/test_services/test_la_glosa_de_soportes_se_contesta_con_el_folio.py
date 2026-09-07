"""Una glosa de soportes se contesta con el folio, no con una declaración.

27-08-2026. El auditor mandó un dictamen real —GL-134, factura HUS0000498954,
causal SO0102— y señaló lo que le faltaba, con sus palabras:

    «Están reclamando un soporte y la IA no responde que realmente, según el
     folio tal de la hoja tal del archivo tal, ahí se encuentra ese
     procedimiento, que lo hizo el Dr. X el día X a X paciente.»

Lo que salió en su lugar fue una declaración categórica —«LA FACTURACIÓN
INCORPORA: (I) FACTURA ELECTRÓNICA... (IX) CUV DEL MINSALUD»— con nueve tipos
de documento y ni un solo folio detrás.

La diferencia es la que decide la glosa: **la entidad no discute lo que está
probado, pero tumba de entrada lo que se afirma sin respaldo** — le basta
pedir el folio.

El motor ya tenía las dos piezas: el Auditor Forense lee el expediente y cita
folios sin inventarlos, y su resultado ya entra al contexto del dictamen. Lo
que faltaba era la obligación de usarlo. Ahora la regla 8.septdecies del
prompt la impone, y esta red comprueba que llegó.
"""

from __future__ import annotations

import pathlib

import pytest

from app.services.glosa_service import (
    _avisar_si_afirma_soportes_sin_probarlos,
    _glosa_es_de_soportes,
)

EVIDENCIA = (
    "═══ EVIDENCIA FORENSE (folios auditados de los soportes) ═══\n"
    "DESCRIPCIÓN QUIRÚRGICA, folio 47, del 12/03/2026, Dr. Pérez.\n"
    "═══ FIN EVIDENCIA FORENSE ═══"
)

# Lo que salió en el dictamen real del auditor.
AFIRMA_EN_BLOQUE = (
    "ESE HUS NO ACEPTA GLOSA POR CONCEPTO DE PRESUNTA FALTA DE SOPORTES DE "
    "FACTURACIÓN, DADO QUE LA FACTURA FUE RADICADA ACOMPAÑADA DE LA TOTALIDAD "
    "DE LOS SOPORTES MÍNIMOS EXIGIDOS. LA FACTURACIÓN INCORPORA: (I) FACTURA "
    "ELECTRÓNICA DE VENTA; (II) AUTORIZACIÓN PREVIA; (III) DOCUMENTO DE IDENTIDAD."
)

# Lo que debería salir.
SEÑALA_EL_FOLIO = (
    "ESE HUS NO ACEPTA LA GLOSA. EL PROCEDIMIENTO OBJETADO SE ENCUENTRA "
    "REGISTRADO EN LA DESCRIPCIÓN QUIRÚRGICA, FOLIO 47, DEL 12 DE MARZO DE "
    "2026, REALIZADO POR EL DR. PÉREZ, LO CUAL DESVIRTÚA LA CAUSAL INVOCADA."
)

GLOSA_SO = (
    "SO0102 - SE GLOSA CONSULTA DE PRIMERA VEZ POR FALTA DE SOPORTES NO EXISTENTE EN LO RADICADO"
)


class TestReconoceLaGlosaDeSoportes:
    def test_por_el_codigo(self):
        assert _glosa_es_de_soportes("SO0102", "")
        assert _glosa_es_de_soportes("SO0101", "")

    def test_por_lo_que_dice_la_entidad_aunque_el_codigo_sea_otro(self):
        assert _glosa_es_de_soportes("", "SE GLOSA POR FALTA DE SOPORTE DE LA ESTANCIA")
        assert _glosa_es_de_soportes("FA0301", "NO EXISTENTE EN LO RADICADO")

    def test_no_se_mete_donde_no_le_toca(self):
        assert not _glosa_es_de_soportes("TA0201", "MAYOR VALOR COBRADO EN LA TARIFA")
        assert not _glosa_es_de_soportes("", "")


class TestAvisaCuandoNoSeñalaDonde:
    def test_habia_evidencia_y_no_se_cito_ni_un_folio(self):
        r = _avisar_si_afirma_soportes_sin_probarlos(
            SEÑALA_EL_FOLIO.replace("FOLIO 47, ", ""), "SO0102", GLOSA_SO, EVIDENCIA
        )
        assert "NO SEÑALA DÓNDE ESTÁ EL SOPORTE" in r, (
            "el folio estaba en el expediente y el escrito no lo nombró: ese es el caso "
            "que más duele"
        )

    def test_afirma_que_mando_todo_sin_probar_nada(self):
        r = _avisar_si_afirma_soportes_sin_probarlos(AFIRMA_EN_BLOQUE, "SO0102", GLOSA_SO, "")
        assert "AFIRMA SIN PROBAR" in r
        assert "pedir el folio" in r

    def test_el_aviso_dice_que_hacer_no_solo_que_esta_mal(self):
        r = _avisar_si_afirma_soportes_sin_probarlos(AFIRMA_EN_BLOQUE, "SO0102", GLOSA_SO, "")
        assert "Auditor Forense" in r, "hay que decirle al gestor con qué resolverlo"


class TestNoMolestaCuandoEstaBien:
    def test_si_cita_el_folio_no_dice_nada(self):
        r = _avisar_si_afirma_soportes_sin_probarlos(SEÑALA_EL_FOLIO, "SO0102", GLOSA_SO, EVIDENCIA)
        assert r == SEÑALA_EL_FOLIO

    @pytest.mark.parametrize(
        "cita", ["OBRA EN LA PÁGINA 12 DEL EXPEDIENTE", "SE ENCUENTRA EN LA HOJA 3"]
    )
    def test_pagina_y_hoja_tambien_cuentan(self, cita: str):
        d = f"ESE HUS NO ACEPTA LA GLOSA. EL SERVICIO {cita}."
        assert _avisar_si_afirma_soportes_sin_probarlos(d, "SO0102", GLOSA_SO, EVIDENCIA) == d

    def test_una_glosa_de_tarifa_no_se_toca(self):
        d = "ESE HUS NO ACEPTA LA GLOSA. EL VALOR COBRADO CORRESPONDE AL PACTADO."
        assert _avisar_si_afirma_soportes_sin_probarlos(d, "TA0201", "MAYOR VALOR", "") == d

    def test_un_dictamen_vacio_no_rompe(self):
        assert _avisar_si_afirma_soportes_sin_probarlos("", "SO0102", GLOSA_SO, "") == ""


class TestLaReglaLlegoAlPrompt:
    """La lección de agosto: escribir la regla nunca fue el trabajo."""

    @pytest.fixture(scope="class")
    def prompt(self) -> str:
        ruta = pathlib.Path(__file__).resolve().parents[2] / "app" / "services"
        return (ruta / "glosa_ia_prompts.py").read_text(encoding="utf-8")

    def test_la_regla_existe(self, prompt: str):
        assert "8.septdecies" in prompt

    def test_obliga_a_nombrar_documento_folio_profesional_y_paciente(self, prompt: str):
        i = prompt.find("8.septdecies")
        bloque = prompt[i : i + 2600].upper()
        for exigido in ("QUÉ DOCUMENTO", "FOLIO", "PROFESIONAL", "PACIENTE"):
            assert exigido in bloque, f"la regla no exige nombrar {exigido}"

    def test_prohibe_la_formula_generica_que_salio_en_el_dictamen(self, prompt: str):
        i = prompt.find("8.septdecies")
        bloque = prompt[i : i + 2600]
        assert "LA FACTURACIÓN INCORPORA" in bloque
        assert "PROHIBIDO" in bloque.upper()

    def test_prohibe_inventar_el_folio(self, prompt: str):
        i = prompt.find("8.septdecies")
        bloque = prompt[i : i + 2600]
        assert "NUNCA un número de folio que no hayas leído" in bloque
