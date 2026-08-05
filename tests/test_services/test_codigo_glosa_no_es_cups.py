"""Un código de glosa no es un CUPS, y el motor no puede confundirlos.

Prueba real del 05-08-2026. Tres dictámenes distintos hablaron de:

    "respecto del servicio facturado con CUPS O0201"
    "Procedimiento médico DE1601"
    "Servicio objetado: Procedimiento quirúrgico/intervencionista CUPS 890701"

O0201 es un código de glosa al que se le perdió la S al copiar (SO0201);
DE1601 es una devolución; y 890701 es una CONSULTA, no una cirugía — esa
descripción se la inventó el modelo.

La causa no estaba en la IA: el código entraba por la ranura del CUPS
ANTES de que el modelo escribiera una palabra. La tabla de familias de
causales que las descarta estaba incompleta.
"""

from __future__ import annotations

from app.utils.parsers_glosa import _extraer_cups_servicio


def _cups(texto: str) -> str:
    return _extraer_cups_servicio(texto)[0]


class TestLosCodigosDeGlosaNoEntranComoCups:
    def test_devolucion_de(self):
        assert _cups("DE1601 FACTURA DEVUELTA POR NO CORRESPONDER A USUARIO") == ""

    def test_codigo_mutilado_de_una_letra(self):
        """«O0201» es «SO0201» al que se le perdió la S al copiar y pegar —
        pasó de verdad, y el dictamen habló del «CUPS O0201»."""
        assert _cups("O0201 FALTA EPICRISIS. VALOR $890.000") == ""

    def test_codigo_de_respuesta_y_de_acuerdo(self):
        assert _cups("RE9901 GLOSA NO ACEPTADA") == ""
        assert _cups("SA5401 ACUERDO DE PAGO") == ""

    def test_las_familias_de_siempre_siguen_descartadas(self):
        for codigo in ("TA0801", "SO0201", "FA0301", "CO0102", "AU0401", "CL0501"):
            assert _cups(f"{codigo} TEXTO DE LA GLOSA") == "", codigo


class TestElCupsRealSigueSaliendo:
    def test_cuando_hay_los_dos_gana_el_cups(self):
        texto = "DE1601 - devolucion - CUPS 890701 - CONSULTA DE URGENCIAS"
        assert _cups(texto) == "890701"

    def test_el_caso_normal_no_cambia(self):
        assert _cups("TA0801 GLOSA POR TARIFA CUPS 890201") == "890201"


class TestElPromptTambienLoDice:
    def test_la_regla_viaja_al_modelo(self):
        from app.services.glosa_ia_prompts import build_user_prompt

        prompt = build_user_prompt(
            texto_glosa="DE1601 FACTURA DEVUELTA POR NO CORRESPONDER A USUARIO",
            contexto_pdf="",
            codigo="DE1601",
            eps="NUEVA EPS",
        )
        assert "NUNCA un CUPS" in prompt
        assert "DE de devoluciones" in prompt
