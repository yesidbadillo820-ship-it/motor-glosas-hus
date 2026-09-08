"""El plazo de 18 meses desde el egreso se cuenta bien, incluidos los bordes.

08-09-2026. Los casos que se le atragantan a una cuenta hecha a mano:

  · el egreso de un 31 en un mes que no tiene 31,
  · el 29 de febrero de un año bisiesto,
  · el corte que cae en domingo o en Semana Santa,
  · el día exacto del vencimiento (¿está o no está prescrita?),
  · el dato malo: sin egreso, con egreso futuro, con fecha ilegible.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services.prescripcion_adres import (
    MESES_PLAZO_ADRES,
    PRESCRITA,
    POR_VENCER,
    VIGENTE,
    evaluar,
    meses_completos_entre,
    sumar_meses,
)


class TestSumarMeses:
    def test_el_caso_corriente(self):
        assert sumar_meses(date(2025, 3, 15), 18) == date(2026, 9, 15)

    def test_un_egreso_del_31_cae_en_el_ultimo_dia_del_mes_corto(self):
        """31 de agosto + 18 meses = 28 de febrero, NO el 3 de marzo."""
        assert sumar_meses(date(2024, 8, 31), 18) == date(2026, 2, 28)
        assert sumar_meses(date(2025, 8, 31), 18) == date(2027, 2, 28)
        # Y si el año de destino es bisiesto, el 29.
        assert sumar_meses(date(2026, 8, 31), 18) == date(2028, 2, 29)

    def test_el_29_de_febrero_bisiesto(self):
        assert sumar_meses(date(2024, 2, 29), 18) == date(2025, 8, 29)
        assert sumar_meses(date(2024, 2, 29), 12) == date(2025, 2, 28)

    def test_el_31_de_diciembre_cruza_bien_de_ano(self):
        assert sumar_meses(date(2024, 12, 31), 18) == date(2026, 6, 30)

    def test_no_pierde_el_dia_en_meses_largos(self):
        assert sumar_meses(date(2025, 1, 31), 18) == date(2026, 7, 31)


class TestMesesTranscurridos:
    def test_cuenta_meses_enteros(self):
        assert meses_completos_entre(date(2025, 1, 15), date(2026, 7, 15)) == 18
        assert meses_completos_entre(date(2025, 1, 15), date(2026, 7, 14)) == 17

    def test_no_cuenta_hacia_atras(self):
        assert meses_completos_entre(date(2026, 7, 15), date(2025, 1, 15)) == 0
        assert meses_completos_entre(date(2026, 7, 15), date(2026, 7, 15)) == 0


class TestElPlazoDeDieciochoMeses:
    def test_una_cuenta_reciente_esta_vigente(self):
        p = evaluar(date(2026, 6, 1), hoy=date(2026, 9, 8))
        assert p is not None
        assert p.estado == VIGENTE and not p.prescrita
        assert p.fecha_corte == date(2027, 12, 1)
        assert p.meses_plazo == MESES_PLAZO_ADRES

    def test_una_cuenta_vieja_esta_prescrita(self):
        p = evaluar(date(2024, 1, 10), hoy=date(2026, 9, 8))
        assert p.prescrita and p.estado == PRESCRITA
        assert p.fecha_corte == date(2025, 7, 10)
        assert p.dias_vencida > 0
        assert p.dias_habiles_restantes == 0
        assert "Prescrita" in p.resumen

    def test_el_dia_exacto_del_vencimiento_todavia_sirve(self):
        """El plazo se agota AL FINAL del último día, no al empezarlo."""
        # Egreso 10-03-2025 → corte 10-09-2026 (jueves, hábil).
        p = evaluar(date(2025, 3, 10), hoy=date(2026, 9, 10))
        assert not p.prescrita
        assert p.dias_restantes == 0
        # Y al día siguiente sí.
        assert evaluar(date(2025, 3, 10), hoy=date(2026, 9, 11)).prescrita

    def test_avisa_antes_de_que_se_venza(self):
        # Corte el 10-09-2026; dos semanas antes ya tiene que estar en rojo.
        p = evaluar(date(2025, 3, 10), hoy=date(2026, 8, 27))
        assert p.estado == POR_VENCER and not p.prescrita
        assert 0 < p.dias_restantes <= 30
        assert p.dias_habiles_restantes < p.dias_restantes  # descontó fines de semana
        assert "Por vencer" in p.resumen


class TestCuandoElCorteCaeEnDiaQueNoSeTrabaja:
    def test_si_vence_en_domingo_el_ultimo_dia_util_es_el_lunes(self):
        # Egreso 06-03-2025 → corte 06-09-2026, que es DOMINGO.
        p = evaluar(date(2025, 3, 6), hoy=date(2026, 9, 1))
        assert p.fecha_corte == date(2026, 9, 6)
        assert p.fecha_corte.weekday() == 6
        assert p.fecha_limite_habil == date(2026, 9, 7)  # lunes
        # El domingo y el lunes todavía no está prescrita.
        assert not evaluar(date(2025, 3, 6), hoy=date(2026, 9, 7)).prescrita
        assert evaluar(date(2025, 3, 6), hoy=date(2026, 9, 8)).prescrita

    def test_si_vence_en_festivo_se_corre_al_siguiente_habil(self):
        # Egreso 20-01-2025 → corte 20-07-2026: Grito de Independencia.
        p = evaluar(date(2025, 1, 20), hoy=date(2026, 7, 1))
        assert p.fecha_corte == date(2026, 7, 20)
        assert p.fecha_limite_habil == date(2026, 7, 21)

    def test_los_festivos_no_mueven_la_fecha_de_corte(self):
        """Un plazo en MESES es de calendario: la Semana Santa no lo estira."""
        p = evaluar(date(2024, 10, 2), hoy=date(2026, 1, 1))
        assert p.fecha_corte == date(2026, 4, 2)  # Jueves Santo de 2026
        assert p.fecha_limite_habil == date(2026, 4, 6)  # lunes tras Semana Santa


class TestDatosMalos:
    def test_sin_egreso_no_se_dictamina(self):
        assert evaluar(None, hoy=date(2026, 9, 8)) is None
        assert evaluar("", hoy=date(2026, 9, 8)) is None
        assert evaluar("   ", hoy=date(2026, 9, 8)) is None

    def test_una_fecha_ilegible_no_se_adivina(self):
        assert evaluar("31/02/2025", hoy=date(2026, 9, 8)) is None
        assert evaluar("ayer", hoy=date(2026, 9, 8)) is None
        assert evaluar("2025-13-01", hoy=date(2026, 9, 8)) is None

    def test_un_egreso_futuro_es_un_dato_malo_no_una_cuenta_vigente(self):
        assert evaluar(date(2026, 12, 1), hoy=date(2026, 9, 8)) is None

    def test_acepta_texto_iso_y_datetime(self):
        esperado = date(2027, 12, 1)
        assert evaluar("2026-06-01", hoy=date(2026, 9, 8)).fecha_corte == esperado
        assert evaluar("2026-06-01 14:30", hoy=date(2026, 9, 8)).fecha_corte == esperado
        assert evaluar("2026-06-01T14:30:00", hoy=date(2026, 9, 8)).fecha_corte == esperado
        assert evaluar(datetime(2026, 6, 1, 14, 30), hoy=date(2026, 9, 8)).fecha_corte == esperado

    def test_un_plazo_de_cero_meses_no_tiene_sentido(self):
        with pytest.raises(ValueError):
            evaluar(date(2025, 1, 1), hoy=date(2026, 9, 8), meses_plazo=0)


class TestSalidaParaLaPantalla:
    def test_el_dict_sale_con_fechas_en_texto(self):
        d = evaluar(date(2024, 1, 10), hoy=date(2026, 9, 8)).a_dict()
        assert d["fecha_egreso"] == "2024-01-10"
        assert d["fecha_corte"] == "2025-07-10"
        assert d["estado"] == PRESCRITA
        assert d["prescrita"] is True
        assert isinstance(d["resumen"], str) and d["resumen"]
        # Nada de objetos date sueltos: tiene que poder viajar como JSON.
        import json

        json.dumps(d)
