"""El modelo del examen tiene que coincidir con el examen real."""

from __future__ import annotations

import pytest

from icfes.dominio import (
    AREAS,
    MINUTOS_POR_SESION,
    ORDEN_AREAS,
    PREGUNTAS_NO_CALIFICABLES,
    SUMA_PESOS,
    TOTAL_PREGUNTAS_CALIFICABLES,
    Area,
    CausaError,
    Dificultad,
    Pregunta,
    preguntas_de_sesion,
    segundos_por_pregunta,
)


def test_el_examen_tiene_254_preguntas_calificables():
    assert TOTAL_PREGUNTAS_CALIFICABLES == 254


def test_el_cuadernillo_completo_trae_278_preguntas():
    assert TOTAL_PREGUNTAS_CALIFICABLES + PREGUNTAS_NO_CALIFICABLES == 278


def test_los_pesos_oficiales_suman_13():
    assert SUMA_PESOS == 13
    assert AREAS[Area.INGLES].peso == 1
    assert all(AREAS[a].peso == 3 for a in ORDEN_AREAS if a is not Area.INGLES)


def test_cantidad_de_preguntas_por_area():
    esperado = {
        Area.LECTURA_CRITICA: 41,
        Area.MATEMATICAS: 50,
        Area.SOCIALES_CIUDADANAS: 50,
        Area.CIENCIAS_NATURALES: 58,
        Area.INGLES: 55,
    }
    assert {a: AREAS[a].preguntas for a in ORDEN_AREAS} == esperado


def test_lectura_critica_va_completa_en_la_primera_sesion():
    assert AREAS[Area.LECTURA_CRITICA].preguntas_sesion_2 == 0
    assert preguntas_de_sesion(1)[Area.LECTURA_CRITICA] == 41


def test_ingles_va_completo_en_la_segunda_sesion():
    assert AREAS[Area.INGLES].preguntas_sesion_1 == 0
    assert preguntas_de_sesion(2)[Area.INGLES] == 55


def test_las_dos_sesiones_suman_el_examen_completo():
    total = sum(preguntas_de_sesion(1).values()) + sum(preguntas_de_sesion(2).values())
    assert total == TOTAL_PREGUNTAS_CALIFICABLES


def test_no_existe_una_tercera_sesion():
    with pytest.raises(ValueError):
        preguntas_de_sesion(3)


def test_hay_algo_mas_de_dos_minutos_por_pregunta():
    # Es el dato que decide la estrategia de tiempo del examen.
    assert 130 <= segundos_por_pregunta(1) <= 140
    assert 118 <= segundos_por_pregunta(2) <= 125
    assert MINUTOS_POR_SESION == 270


def _pregunta(**cambios):
    base = {
        "id": "X-1",
        "area": Area.MATEMATICAS,
        "competencia": "Argumentación",
        "componente": "Aleatorio",
        "tema": "Probabilidad",
        "dificultad": Dificultad.MEDIA,
        "enunciado": "¿Cuál es?",
        "opciones": ("a", "b", "c", "d"),
        "correcta": 0,
        "explicacion": "Una explicación suficientemente larga para que sirva de algo.",
        "trampa": "El distractor.",
    }
    base.update(cambios)
    return Pregunta(**base)


def test_una_pregunta_valida_se_construye():
    p = _pregunta()
    assert p.letra_correcta == "A"
    assert p.es_correcta(0) and not p.es_correcta(1)


def test_rechaza_pregunta_sin_cuatro_opciones():
    with pytest.raises(ValueError, match="4 opciones"):
        _pregunta(opciones=("a", "b", "c"))


def test_rechaza_respuesta_fuera_de_rango():
    with pytest.raises(ValueError, match="de 0 a 3"):
        _pregunta(correcta=7)


def test_rechaza_competencia_que_no_existe_en_el_area():
    with pytest.raises(ValueError, match="no existe"):
        _pregunta(competencia="Inventada")


def test_rechaza_componente_que_no_existe_en_el_area():
    with pytest.raises(ValueError, match="no existe"):
        _pregunta(componente="Inventado")


def test_rechaza_pregunta_sin_explicacion():
    with pytest.raises(ValueError, match="sin explicación"):
        _pregunta(explicacion="   ")


def test_toda_causa_de_error_trae_descripcion_y_remedio():
    for causa in CausaError:
        assert causa.descripcion.strip()
        assert causa.remedio.strip()
