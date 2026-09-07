"""Pruebas 1 y 3 del 02-09, la parte que quedaba.

Prueba 1 (TA0301, La Previsora). La plantilla fija de tarifa sin contrato
decía «MANUAL TARIFARIO SOAT 2026 INDEXADO A UVB — VALOR UVB 2026: $12.110»
en un dictamen SIN fecha de prestación. Sin la fecha no se sabe qué UVB rige:
una atención de 2025 va con la UVB de 2025. El auditor lo dijo: que venga de
una plantilla y no de la IA no lo hace menos grave — la entidad tumba el
dictamen igual pidiendo la liquidación.

Prueba 3 (AU0201, FAMISANAR). Con dos PDF recién leídos, debajo salía «⏳ EL
ÍNDICE SE ESTÁ RECONSTRUYENDO» y el auditor entendió que el motor no había
leído nada — cuando el triage venía justamente de ese PDF. Son dos cosas
distintas y ahora se dicen con todas las letras.
"""

from __future__ import annotations

import datetime as dt
import io


from app.services.glosa_service import _frase_uvb_segun_fecha, generar_texto_injustificada


class TestLaUvbNoSeAfirmaAOjo:
    def test_sin_fecha_no_afirma_el_valor_ni_el_anio(self):
        t = generar_texto_injustificada("LA PREVISORA", "TA0301", "$ 1.254.000")
        assert "12.110" not in t
        assert "SOAT 2026" not in t
        assert "CONFIRMAR CON LA FECHA DEL SERVICIO" in t

    def test_con_fecha_de_2026_va_el_valor(self):
        t = generar_texto_injustificada(
            "LA PREVISORA", "TA0301", "$ 1.254.000", fecha_hecho=dt.date(2026, 5, 1)
        )
        assert "VALOR UVB 2026: $12.110" in t

    def test_con_fecha_de_otro_anio_nombra_ese_anio_y_no_el_valor_de_2026(self):
        t = generar_texto_injustificada(
            "LA PREVISORA", "TA0301", "$ 1.254.000", fecha_hecho=dt.date(2025, 8, 1)
        )
        assert "12.110" not in t
        assert "VIGENTE EN 2025" in t

    def test_la_norma_se_cita_en_los_tres_casos(self):
        for f in (None, dt.date(2026, 1, 1), dt.date(2025, 1, 1)):
            assert "CIRCULAR EXTERNA 047 DE 2025" in _frase_uvb_segun_fecha(f)

    def test_sigue_diciendo_soat_plena_porque_eso_si_es_cierto_sin_contrato(self):
        """Lo que no se sabe es la UVB del año, no que aplique SOAT pleno."""
        t = generar_texto_injustificada("LA PREVISORA", "TA0301", "$ 1.254.000")
        assert "TARIFA SOAT PLENA" in t

    def test_una_fecha_rara_no_rompe(self):
        assert "CIRCULAR" in _frase_uvb_segun_fecha("no es fecha")
        assert "CIRCULAR" in _frase_uvb_segun_fecha(None)

    def test_el_motor_le_pasa_la_fecha_del_formulario(self):
        """La llamada va por un helper de una línea: hay otra prueba que mira
        una ventana fija de texto antes de `tipo_glosa = "TA_TARIFA"`."""
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        i = motor.index("argumento_fijo = generar_texto_injustificada(")
        assert "fecha_hecho=_fecha_del_formulario(data)," in motor[i : i + 300]
        j = motor.index("def _fecha_del_formulario(data):")
        helper = motor[j : j + 900]
        assert 'getattr(data, "fecha_radicacion", None)' in helper
        assert 'getattr(data, "fecha_recepcion", None)' in helper


class TestElAvisoDelIndiceYaNoDesmienteLoLeido:
    def test_con_anexos_se_aclara_antes_del_aviso(self):
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        i = motor.index('bloque_adjuntos = _bloque_anexos + _aclaracion + (aviso_adj or "")')
        bloque = motor[i - 1200 : i]
        assert "sí se leyeron</b>" in bloque
        # En el fuente va partido en dos cadenas con <b> en medio.
        assert "El aviso siguiente es sobre el <b>expediente " in bloque
        assert "institucional</b> de la factura" in bloque
        assert "no sobre lo que usted adjuntó" in bloque

    def test_la_aclaracion_solo_sale_si_hay_aviso(self):
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        i = motor.index('_aclaracion = ""')
        assert "if aviso_adj:" in motor[i : i + 200]

    def test_el_orden_es_anexos_aclaracion_aviso(self):
        """Primero lo que sí se leyó, después la aclaración, y al final el aviso."""
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert 'bloque_adjuntos = _bloque_anexos + _aclaracion + (aviso_adj or "")' in motor
