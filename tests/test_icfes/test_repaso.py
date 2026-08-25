"""El repaso espaciado decide qué se recuerda el día del examen."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from icfes.dominio import CausaError
from icfes.repaso import (
    CALIDAD_APROBATORIA,
    FACILIDAD_MINIMA,
    Tarjeta,
    calidad_desde_respuesta,
    calificar,
    carga_proxima,
    pendientes,
)

HOY = date(2026, 8, 20)
EXAMEN = date(2027, 8, 8)


def test_una_tarjeta_nueva_vence_de_una():
    t = Tarjeta("MAT-001")
    assert t.es_nueva
    assert t.vence(HOY)


def test_el_primer_acierto_programa_para_manana():
    t = calificar(Tarjeta("X"), 5, HOY, EXAMEN)
    assert t.intervalo_dias == 1
    assert t.proxima_fecha == HOY + timedelta(days=1)


def test_el_segundo_acierto_programa_a_seis_dias():
    t = calificar(calificar(Tarjeta("X"), 5, HOY, EXAMEN), 5, HOY, EXAMEN)
    assert t.intervalo_dias == 6


def test_los_intervalos_crecen_con_los_aciertos():
    t = Tarjeta("X")
    dia = HOY
    intervalos = []
    for _ in range(5):
        t = calificar(t, 5, dia, EXAMEN)
        intervalos.append(t.intervalo_dias)
        dia = t.proxima_fecha
    assert intervalos == sorted(intervalos)
    assert intervalos[-1] > intervalos[0]


def test_fallar_reinicia_el_ciclo():
    t = Tarjeta("X")
    for _ in range(4):
        t = calificar(t, 5, HOY, EXAMEN)
    fallada = calificar(t, 1, HOY, EXAMEN)
    assert fallada.repeticiones == 0
    assert fallada.intervalo_dias == 1


def test_fallar_baja_la_facilidad_pero_nunca_del_minimo():
    t = Tarjeta("X")
    for _ in range(20):
        t = calificar(t, 0, HOY, EXAMEN)
    assert t.facilidad == pytest.approx(FACILIDAD_MINIMA)


def test_acertar_sube_la_facilidad():
    t = calificar(Tarjeta("X"), 5, HOY, EXAMEN)
    assert t.facilidad > Tarjeta("X").facilidad


def test_ningun_repaso_queda_programado_despues_del_examen():
    # Es la regla que distingue este repaso de uno genérico.
    t = Tarjeta("X", repeticiones=9, facilidad=2.8, intervalo_dias=300)
    resultado = calificar(t, 5, EXAMEN - timedelta(days=20), EXAMEN)
    assert resultado.proxima_fecha < EXAMEN


def test_sin_fecha_de_examen_el_intervalo_no_se_recorta():
    t = Tarjeta("X", repeticiones=9, facilidad=2.8, intervalo_dias=300)
    resultado = calificar(t, 5, HOY)
    assert resultado.proxima_fecha > EXAMEN


def test_calidad_invalida_es_error():
    with pytest.raises(ValueError):
        calificar(Tarjeta("X"), 9, HOY)


def test_calidad_segun_por_que_se_fallo():
    assert calidad_desde_respuesta(False, causa=CausaError.CONCEPTO) == 0
    assert calidad_desde_respuesta(False, causa=CausaError.ADIVINE) == 0
    assert calidad_desde_respuesta(False, causa=CausaError.DESCUIDO) == 2
    assert calidad_desde_respuesta(False) == 1


def test_calidad_segun_lo_rapido_que_se_acerto():
    assert calidad_desde_respuesta(True, segundos=30) == 5
    assert calidad_desde_respuesta(True, segundos=100) == 4
    assert calidad_desde_respuesta(True, segundos=400) == 3
    assert calidad_desde_respuesta(True) == 4


def test_fallar_siempre_da_menos_del_umbral_de_aprobacion():
    for causa in list(CausaError) + [None]:
        assert calidad_desde_respuesta(False, causa=causa) < CALIDAD_APROBATORIA


def test_los_pendientes_salen_de_lo_mas_atrasado_a_lo_menos():
    tarjetas = [
        Tarjeta("nueva"),
        Tarjeta("vieja", proxima_fecha=HOY - timedelta(days=10)),
        Tarjeta("de_ayer", proxima_fecha=HOY - timedelta(days=1)),
        Tarjeta("futura", proxima_fecha=HOY + timedelta(days=5)),
    ]
    claves = [t.clave for t in pendientes(tarjetas, HOY)]
    assert claves == ["nueva", "vieja", "de_ayer"]


def test_los_pendientes_respetan_el_limite():
    tarjetas = [Tarjeta(f"t{i}", proxima_fecha=HOY) for i in range(50)]
    assert len(pendientes(tarjetas, HOY, limite=12)) == 12


def test_la_carga_proxima_avisa_cuantos_repasos_caen_cada_dia():
    tarjetas = [
        Tarjeta("a", proxima_fecha=HOY),
        Tarjeta("b", proxima_fecha=HOY),
        Tarjeta("c", proxima_fecha=HOY + timedelta(days=3)),
        Tarjeta("d", proxima_fecha=HOY + timedelta(days=99)),
    ]
    agenda = carga_proxima(tarjetas, HOY, dias=7)
    assert agenda[HOY] == 2
    assert agenda[HOY + timedelta(days=3)] == 1
    assert sum(agenda.values()) == 3


def test_lo_atrasado_se_cuenta_para_hoy():
    tarjetas = [Tarjeta("a", proxima_fecha=HOY - timedelta(days=30))]
    assert carga_proxima(tarjetas, HOY, dias=3)[HOY] == 1


def test_mirar_cero_dias_es_error():
    with pytest.raises(ValueError):
        carga_proxima([], HOY, dias=0)
