"""Dos objeciones que no pueden ser ciertas a la vez.

OT-004 · 05-08-2026. Glosa de prueba de SALUD MIA: FA0302 "servicio no
prestado" y TA0801 "tarifa superior a la pactada" sobre el MISMO ítem.

Si el servicio no se prestó no hay tarifa que discutir; si la tarifa está
mal, el servicio se prestó. La entidad se contradice y esa contradicción
sola tumba las dos objeciones — pero el motor refutó cada una por separado
y nunca lo dijo.
"""

from __future__ import annotations

from app.services.glosa_service import _contradiccion_no_prestado_vs_tarifa as _contra

GLOSA_SALUD_MIA = (
    "SALUD MIA — FA0302: COBRO DE SERVICIO NO PRESTADO. TA0801: TARIFA "
    "SUPERIOR A LA PACTADA EN EL CONTRATO. VALOR $4.200.000."
)


class TestSeDetectaLaContradiccion:
    def test_el_caso_real_salud_mia(self):
        assert _contra(GLOSA_SALUD_MIA) is True

    def test_sin_tildes_tambien(self):
        assert _contra("EL PROCEDIMIENTO NO SE REALIZO Y ADEMAS HAY SOBRECOSTO") is True
        assert _contra("EL PROCEDIMIENTO NO SE REALIZÓ Y ADEMÁS HAY SOBRECOSTO") is True

    def test_otras_formas_de_decirlo(self):
        for t in (
            "SERVICIO NO SUMINISTRADO. MAYOR VALOR COBRADO FRENTE AL ANEXO 3.",
            "PROCEDIMIENTO NO REALIZADO Y VALOR SUPERIOR AL PACTADO.",
            "SERVICIO INEXISTENTE — DIFERENCIA TARIFARIA CON EL MANUAL.",
        ):
            assert _contra(t) is True, t


class TestUnaSolaObjecionNoEsContradiccion:
    def test_solo_no_prestado(self):
        assert _contra("FA0302 — COBRO DE SERVICIO NO PRESTADO. VALOR $500.000.") is False

    def test_solo_tarifa(self):
        assert _contra("TA0801 — TARIFA SUPERIOR A LA PACTADA. SOAT UVB -5%.") is False

    def test_texto_vacio(self):
        assert _contra("") is False
        assert _contra(None) is False

    def test_glosa_de_soportes_no_dispara(self):
        assert _contra("SO0201 — FALTA EPICRISIS Y HOJA DE ADMINISTRACIÓN.") is False


class TestElAvisoEstaEnchufado:
    def test_el_dictamen_lo_agrega(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_contradiccion_no_prestado_vs_tarifa(" in src
        i = src.index("_contradiccion_no_prestado_vs_tarifa(texto_base")
        bloque = src[max(0, i - 600) : i + 1800]
        assert "LA GLOSA SE " in bloque
        assert "GLOSA-CONTRADICTORIA" in bloque, "un fallo no puede tumbar el dictamen"

    def test_no_decide_por_el_auditor(self):
        """Como los demás avisos: señala el hecho, no cambia la respuesta."""
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        i = src.index("_contradiccion_no_prestado_vs_tarifa(texto_base")
        bloque = src[i : i + 1800]
        assert "dictamen = dictamen + (" in bloque
        assert "modo_resp" not in bloque, "el aviso no toca el modo de respuesta"
