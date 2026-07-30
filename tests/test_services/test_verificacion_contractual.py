"""El sistema detecta contratos vencidos ANTES de emitir el dictamen.

La cadena completa: la fecha del formulario (radicación o recepción) viaja
hasta la resolución del contrato, la malla decide cuál regía ese día, y si
ninguno lo cubría el prompt recibe la alerta de vigencia en vez del contrato
muerto. Antes la fecha existía en el formulario y nadie la usaba: el dictamen
citaba el contrato de hoy para una atención de hace meses.
"""

from __future__ import annotations

import datetime as dt

from app.services.glosa_ia_prompts import (
    build_user_prompt,
    get_contrato,
    get_system_prompt,
    validar_factura_en_vigencia,
)


class TestElContratoSeResuelveALaFecha:
    def test_compensar_en_vigencia_usa_su_contrato(self):
        c = get_contrato("COMPENSAR", dt.date(2025, 9, 15))
        assert "CSS009-2024" in c["numero"]
        assert c["factor"] == 0.85

    def test_compensar_vencido_no_se_cita(self):
        """Después del 3-abr-2026 no hay contrato: SOAT pleno y la explicación."""
        c = get_contrato("COMPENSAR", dt.date(2026, 7, 29))
        assert c["numero"] == "SIN CONTRATO PACTADO"
        assert c["factor"] == 1.00
        assert "CSS009-2024" in c["nota"]

    def test_acepta_fecha_como_texto_y_como_datetime(self):
        """El formulario manda date; otros llamadores mandan texto ISO."""
        por_date = get_contrato("COOSALUD", dt.date(2026, 6, 15))
        por_texto = get_contrato("COOSALUD", "2026-06-15")
        por_datetime = get_contrato("COOSALUD", dt.datetime(2026, 6, 15, 10, 30))
        assert por_date["numero"] == por_texto["numero"] == por_datetime["numero"]


class TestLaValidacionUsaLaMalla:
    """`validar_factura_en_vigencia` parseaba la vigencia desde TEXTO libre
    ('2025', '15/04/2026 — 14/04/2027'). Ahora la malla —fechas reales—
    manda, y el texto queda de respaldo para pagadores fuera de ella."""

    def test_dentro_de_vigencia_dice_que_contrato_cubre(self):
        v = validar_factura_en_vigencia("COMPENSAR", "2025-09-15")
        assert v["en_vigencia"] is True
        assert "CSS009-2024" in v["diagnostico"]
        assert "malla oficial" in v["diagnostico"]

    def test_fuera_de_vigencia_lo_dice_con_las_fechas(self):
        v = validar_factura_en_vigencia("FAMISANAR", "20/03/2026")
        assert v["en_vigencia"] is False
        assert "malla oficial" in v["diagnostico"]
        # Y nombra el contrato que existe, con sus fechas, para que el
        # auditor entienda qué pasó.
        assert "S13103104958" in v["diagnostico"]

    def test_pagador_fuera_de_la_malla_cae_al_respaldo(self):
        """Un pagador desconocido no revienta: sigue el camino viejo."""
        v = validar_factura_en_vigencia("EPS INVENTADA XYZ", "2026-01-15")
        assert "en_vigencia" in v  # no importa el veredicto: importa que responda


class TestLaAlertaLlegaAlPrompt:
    """Si la fecha cae fuera de vigencia, el prompt que recibe la IA trae la
    alerta y la instrucción de NO citar el contrato muerto."""

    def test_el_user_prompt_trae_la_alerta_cuando_no_hay_vigencia(self):
        prompt = build_user_prompt(
            texto_glosa="Se glosa por tarifas la factura",
            contexto_pdf="Fecha de atención: 29/07/2026 en urgencias",
            codigo="TA0201",
            eps="COMPENSAR",
            numero_factura="HUS0000443697",
            fecha_hecho=dt.date(2026, 7, 29),
        )
        assert "ALERTA DE VIGENCIA" in prompt
        assert "NO cites ese contrato" in prompt

    def test_el_user_prompt_normal_no_trae_alerta(self):
        prompt = build_user_prompt(
            texto_glosa="Se glosa por tarifas la factura",
            contexto_pdf="Fecha de atención: 15/09/2025 en urgencias",
            codigo="TA0201",
            eps="COMPENSAR",
            numero_factura="HUS0000443697",
            fecha_hecho=dt.date(2025, 9, 15),
        )
        assert "ALERTA DE VIGENCIA" not in prompt
        assert "CSS009-2024" in prompt

    def test_el_system_prompt_usa_el_factor_del_dia(self):
        """El factor que la IA convierte en pesos es el del contrato que
        regía, no el de hoy."""
        con_contrato = get_system_prompt("TA", "COMPENSAR", dt.date(2025, 9, 15))
        assert "CALCULADORA TARIFARIA" in con_contrato
        sin_contrato = get_system_prompt("TA", "COMPENSAR", dt.date(2026, 7, 29))
        # factor 1.0 → no hay descuento que calcular: la calculadora de
        # factor pactado no aplica.
        assert "factor_contractual" not in sin_contrato or "SOAT" in sin_contrato
