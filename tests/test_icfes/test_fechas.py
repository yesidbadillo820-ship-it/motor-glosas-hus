"""Las fechas se muestran en español, sin depender del idioma del sistema."""

from __future__ import annotations

from datetime import date

from icfes import fechas


def test_dia_de_la_semana_en_espanol():
    assert fechas.dia_semana(date(2026, 8, 20)) == "jueves"
    assert fechas.dia_semana(date(2026, 8, 23)) == "domingo"


def test_dia_corto():
    assert fechas.dia_semana(date(2026, 8, 20), corto=True) == "jue"


def test_mes_en_espanol():
    assert fechas.mes(date(2026, 8, 20)) == "agosto"
    assert fechas.mes(date(2026, 12, 1)) == "diciembre"


def test_fecha_larga():
    assert fechas.largo(date(2027, 8, 8)) == "domingo 8 de agosto de 2027"


def test_fecha_corta():
    assert fechas.corto(date(2026, 8, 20)) == "jue 20/08"


def test_cuenta_regresiva_con_semanas():
    texto = fechas.cuenta_regresiva(date(2026, 8, 20), date(2027, 8, 8))
    assert "353 días" in texto
    assert "50 semanas" in texto


def test_cuenta_regresiva_de_pocos_dias():
    assert fechas.cuenta_regresiva(date(2027, 8, 3), date(2027, 8, 8)) == "Faltan 5 días."


def test_cuenta_regresiva_de_un_solo_dia():
    assert fechas.cuenta_regresiva(date(2027, 8, 7), date(2027, 8, 8)) == "Falta 1 día."


def test_el_dia_del_examen():
    assert "HOY" in fechas.cuenta_regresiva(date(2027, 8, 8), date(2027, 8, 8))


def test_despues_del_examen():
    assert "ya pasó" in fechas.cuenta_regresiva(date(2027, 9, 1), date(2027, 8, 8))


def test_semanas_exactas_sin_dias_sueltos():
    texto = fechas.cuenta_regresiva(date(2027, 7, 25), date(2027, 8, 8))
    assert "2 semanas" in texto and " y " not in texto
