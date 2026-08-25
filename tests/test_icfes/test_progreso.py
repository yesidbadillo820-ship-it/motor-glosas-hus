"""Medir el avance sin engañar: ni optimismo ni pesimismo."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from icfes.dominio import ORDEN_AREAS, Area, CausaError
from icfes.progreso import (
    MINIMO_PARA_PROYECTAR,
    Intento,
    cuaderno_errores,
    dominio_por_area,
    dominio_por_competencia,
    informe,
    proyectar,
    puntos_debiles,
    racha,
    reincidentes,
    temas_a_reforzar,
)

HOY = date(2027, 3, 15)
EXAMEN = date(2027, 8, 8)


def _intento(
    dias_atras=0,
    acerto=True,
    area=Area.MATEMATICAS,
    competencia="Argumentación",
    tema="Porcentajes",
    pregunta="MAT-001",
    causa=None,
):
    return Intento(
        fecha=HOY - timedelta(days=dias_atras),
        pregunta_id=pregunta,
        area=area,
        competencia=competencia,
        tema=tema,
        acerto=acerto,
        segundos=90.0,
        causa=causa,
    )


def test_sin_intentos_no_hay_dominio_medible():
    dominios = dominio_por_area([], HOY)
    assert all(not d.medible for d in dominios.values())
    assert all(d.etiqueta == "sin datos suficientes" for d in dominios.values())


def test_el_dominio_aparece_para_las_cinco_areas():
    assert set(dominio_por_area([], HOY)) == set(ORDEN_AREAS)


def test_lo_reciente_pesa_mas_que_lo_viejo():
    # Falló hace mucho y acierta ahora: el dominio debe verse alto.
    intentos = [_intento(dias_atras=200, acerto=False) for _ in range(10)]
    intentos += [_intento(dias_atras=0, acerto=True) for _ in range(10)]
    d = dominio_por_area(intentos, HOY)[Area.MATEMATICAS]
    assert d.proporcion > 0.8
    # Y al revés: acertó hace mucho y falla ahora.
    invertido = [_intento(dias_atras=200, acerto=True) for _ in range(10)]
    invertido += [_intento(dias_atras=0, acerto=False) for _ in range(10)]
    assert dominio_por_area(invertido, HOY)[Area.MATEMATICAS].proporcion < 0.2


def test_con_pocos_intentos_el_dominio_no_se_declara_medible():
    d = dominio_por_area([_intento()], HOY)[Area.MATEMATICAS]
    assert not d.medible


def test_dominio_por_competencia_separa_competencias():
    intentos = [
        _intento(competencia="Argumentación", acerto=False),
        _intento(competencia="Argumentación", acerto=False),
        _intento(competencia="Formulación y ejecución", acerto=True),
    ]
    dominios = dominio_por_competencia(intentos, HOY)
    assert dominios["Argumentación"].proporcion == 0.0
    assert dominios["Formulación y ejecución"].proporcion == 1.0


def test_los_puntos_debiles_salen_de_peor_a_mejor():
    intentos = [_intento(competencia="Argumentación", acerto=False) for _ in range(5)]
    intentos += [_intento(competencia="Formulación y ejecución", acerto=True) for _ in range(5)]
    debiles = puntos_debiles(intentos, HOY)
    assert debiles[0].nombre == "Argumentación"


def test_los_temas_a_reforzar_ordenan_por_fallas():
    intentos = [_intento(tema="Probabilidad", acerto=False) for _ in range(4)]
    intentos += [_intento(tema="Áreas", acerto=False) for _ in range(2)]
    intentos += [_intento(tema="Escalas", acerto=True) for _ in range(3)]
    temas = temas_a_reforzar(intentos)
    assert temas[0][0] == "Probabilidad"
    assert "Escalas" not in [t[0] for t in temas]


def test_el_cuaderno_agrupa_por_causa_y_trae_el_remedio():
    intentos = [_intento(acerto=False, causa=CausaError.TIEMPO) for _ in range(3)]
    intentos += [_intento(acerto=False, causa=CausaError.CONCEPTO)]
    cuaderno = cuaderno_errores(intentos)
    assert cuaderno[0].causa is CausaError.TIEMPO
    assert cuaderno[0].veces == 3
    assert cuaderno[0].porcentaje == pytest.approx(75.0)
    assert cuaderno[0].remedio.strip()


def test_los_aciertos_no_entran_al_cuaderno_de_errores():
    assert cuaderno_errores([_intento(acerto=True)]) == []


def test_las_fallas_sin_causa_no_entran_al_cuaderno():
    assert cuaderno_errores([_intento(acerto=False, causa=None)]) == []


def test_las_preguntas_falladas_varias_veces_se_marcan():
    intentos = [_intento(pregunta="MAT-007", acerto=False) for _ in range(3)]
    intentos += [_intento(pregunta="MAT-008", acerto=False)]
    assert reincidentes(intentos) == [("MAT-007", 3)]


def test_la_racha_cuenta_dias_seguidos():
    intentos = [_intento(dias_atras=d) for d in range(5)]
    assert racha(intentos, HOY) == 5


def test_la_racha_no_se_rompe_si_hoy_todavia_no_se_ha_estudiado():
    intentos = [_intento(dias_atras=d) for d in range(1, 4)]
    assert racha(intentos, HOY) == 3


def test_la_racha_se_rompe_con_dos_dias_sin_estudiar():
    intentos = [_intento(dias_atras=d) for d in (2, 3, 4)]
    assert racha(intentos, HOY) == 0


def test_sin_intentos_la_racha_es_cero():
    assert racha([], HOY) == 0


def test_con_un_solo_simulacro_no_se_proyecta():
    p = proyectar([(date(2026, 11, 1), 250)], EXAMEN, 400)
    assert not p.confiable
    assert "no hay tendencia" in p.mensaje


def test_sin_simulacros_no_hay_proyeccion():
    p = proyectar([], EXAMEN, 400)
    assert p.puntaje_proyectado is None


def test_una_tendencia_creciente_proyecta_hacia_arriba():
    historial = [
        (date(2026, 11, 1), 250),
        (date(2027, 1, 10), 275),
        (date(2027, 3, 1), 305),
    ]
    p = proyectar(historial, EXAMEN, 400)
    assert p.confiable
    assert p.puntaje_proyectado > 305
    assert p.puntos_por_mes > 0


def test_la_proyeccion_avisa_cuando_no_alcanza_la_meta():
    historial = [
        (date(2026, 11, 1), 250),
        (date(2027, 1, 10), 255),
        (date(2027, 3, 1), 260),
    ]
    p = proyectar(historial, EXAMEN, 450)
    assert "faltarían" in p.mensaje


def test_la_proyeccion_avisa_cuando_no_se_esta_subiendo():
    historial = [
        (date(2026, 11, 1), 300),
        (date(2027, 1, 10), 290),
        (date(2027, 3, 1), 280),
    ]
    p = proyectar(historial, EXAMEN, 400)
    assert "no está subiendo" in p.mensaje


def test_la_proyeccion_no_se_sale_de_la_escala():
    historial = [
        (date(2026, 11, 1), 100),
        (date(2026, 12, 1), 300),
        (date(2027, 1, 1), 490),
    ]
    p = proyectar(historial, EXAMEN, 400)
    assert 0 <= p.puntaje_proyectado <= 500


def test_simulacros_del_mismo_dia_no_dan_tendencia():
    historial = [(date(2027, 1, 1), 300), (date(2027, 1, 1), 320)]
    p = proyectar(historial, EXAMEN, 400)
    assert not p.confiable
    assert "mismo día" in p.mensaje


def test_hacen_falta_tres_simulacros_para_confiar():
    historial = [(date(2026, 11, 1), 250), (date(2027, 1, 1), 300)]
    p = proyectar(historial, EXAMEN, 400)
    assert not p.confiable
    assert str(MINIMO_PARA_PROYECTAR) in p.mensaje


def test_el_informe_funciona_aunque_no_haya_nada():
    texto = informe([], [], HOY, EXAMEN, 400)
    assert "INFORME DE PROGRESO" in texto
    assert "Meta: 400" in texto


def test_el_informe_reune_todo_lo_importante():
    intentos = [_intento(dias_atras=d, acerto=d % 2 == 0) for d in range(10)]
    intentos += [_intento(acerto=False, causa=CausaError.TIEMPO) for _ in range(3)]
    historial = [
        (date(2026, 11, 1), 250),
        (date(2027, 1, 10), 275),
        (date(2027, 3, 1), 305),
    ]
    texto = informe(intentos, historial, HOY, EXAMEN, 400)
    for esperado in ("Racha", "DOMINIO POR ÁREA", "POR QUÉ ESTOY FALLANDO", "Proyección"):
        assert esperado in texto
