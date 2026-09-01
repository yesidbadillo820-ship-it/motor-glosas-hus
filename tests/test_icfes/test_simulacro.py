"""Los simulacros deben imitar la estructura y el tiempo del examen real."""

from __future__ import annotations

from datetime import date

import pytest

from icfes.dominio import ORDEN_AREAS, Area, preguntas_de_sesion
from icfes.simulacro import (
    TipoSimulacro,
    armar_simulacro,
    calificar_simulacro,
    descripcion_estimacion,
)

HOY = date(2026, 8, 20)


def test_la_sesion_1_no_trae_ingles(banco):
    s = armar_simulacro(banco, TipoSimulacro.SESION_1, semilla=1)
    assert Area.INGLES not in s.reparto
    assert Area.LECTURA_CRITICA in s.reparto


def test_la_sesion_2_no_trae_lectura_critica(banco):
    s = armar_simulacro(banco, TipoSimulacro.SESION_2, semilla=1)
    assert Area.LECTURA_CRITICA not in s.reparto
    assert Area.INGLES in s.reparto


def test_el_simulacro_completo_trae_las_cinco_areas(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=1)
    assert set(s.reparto) == set(ORDEN_AREAS)


def test_el_reparto_oficial_coincide_con_el_examen(banco):
    s = armar_simulacro(banco, TipoSimulacro.SESION_1, semilla=1)
    assert s.reparto_oficial == preguntas_de_sesion(1)


def test_el_simulacro_a_escala_conserva_las_proporciones(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=2, maximo=50)
    oficial = s.reparto_oficial
    mayor_oficial = max(oficial, key=lambda a: oficial[a])
    mayor_real = max(s.reparto, key=lambda a: s.reparto[a])
    assert mayor_oficial is mayor_real


def test_el_tiempo_por_pregunta_es_el_del_examen(banco):
    s1 = armar_simulacro(banco, TipoSimulacro.SESION_1, semilla=1)
    s2 = armar_simulacro(banco, TipoSimulacro.SESION_2, semilla=1)
    assert s1.segundos_por_pregunta() == pytest.approx(135, abs=1)
    assert s2.segundos_por_pregunta() == pytest.approx(121, abs=1)


def test_un_simulacro_a_escala_lo_dice_en_el_aviso(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=1, maximo=30)
    assert not s.es_tamano_real
    assert "escala" in s.aviso.lower()
    assert "NO entrena el cansancio" in s.aviso


def test_el_tope_de_preguntas_se_respeta(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=3, maximo=25)
    assert s.total <= 30  # el redondeo por área puede sumar una o dos


def test_no_se_repiten_preguntas_dentro_de_un_simulacro(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=4)
    assert len({p.id for p in s.preguntas}) == s.total


def test_la_misma_semilla_arma_el_mismo_simulacro(banco):
    a = armar_simulacro(banco, TipoSimulacro.SESION_1, semilla=8)
    b = armar_simulacro(banco, TipoSimulacro.SESION_1, semilla=8)
    assert [p.id for p in a.preguntas] == [p.id for p in b.preguntas]


def test_simulacro_de_una_sola_area(banco):
    s = armar_simulacro(banco, TipoSimulacro.AREA, area=Area.MATEMATICAS, semilla=1)
    assert set(s.reparto) == {Area.MATEMATICAS}
    assert all(p.area is Area.MATEMATICAS for p in s.preguntas)


def test_simulacro_de_area_sin_decir_cual_es_error(banco):
    with pytest.raises(ValueError, match="cuál área"):
        armar_simulacro(banco, TipoSimulacro.AREA, semilla=1)


def test_todo_correcto_da_100_en_cada_area(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=5, maximo=40)
    respuestas = {p.id: p.correcta for p in s.preguntas}
    r = calificar_simulacro(s, respuestas, HOY)
    assert r.correctas == r.total
    assert all(area.puntaje == 100 for area in r.por_area.values())
    assert r.global_estimado == 500


def test_no_responder_cuenta_como_fallar(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=6, maximo=40)
    r = calificar_simulacro(s, {}, HOY)
    assert r.correctas == 0
    assert r.global_estimado == 0


def test_sin_todas_las_areas_no_hay_puntaje_global(banco):
    s = armar_simulacro(banco, TipoSimulacro.SESION_1, semilla=7)
    r = calificar_simulacro(s, {}, HOY)
    assert not r.tiene_todas_las_areas
    assert r.global_estimado is None
    assert "No se calcula puntaje global" in r.informe()


def test_el_informe_muestra_las_competencias_mas_flojas(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=9, maximo=60)
    # Falla todo lo de Matemáticas y acierta el resto.
    respuestas = {
        p.id: (p.correcta if p.area is not Area.MATEMATICAS else (p.correcta + 1) % 4)
        for p in s.preguntas
    }
    r = calificar_simulacro(s, respuestas, HOY)
    assert r.por_area[Area.MATEMATICAS].correctas == 0
    assert "COMPETENCIAS MÁS FLOJAS" in r.informe()


def test_el_informe_dice_el_nivel_de_ingles(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=10, maximo=40)
    respuestas = {p.id: p.correcta for p in s.preguntas}
    assert "nivel estimado B1" in calificar_simulacro(s, respuestas, HOY).informe()


def test_el_informe_avisa_cuando_va_a_escala(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=11, maximo=30)
    texto = calificar_simulacro(s, {}, HOY).informe()
    assert "escala" in texto.lower()


def test_el_informe_reporta_el_tiempo_usado(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=12, maximo=30)
    texto = calificar_simulacro(s, {}, HOY, segundos_usados=1800).informe()
    assert "30 minutos" in texto


def test_la_descripcion_del_area_se_declara_como_estimacion(banco):
    s = armar_simulacro(banco, TipoSimulacro.COMPLETO, semilla=13, maximo=40)
    r = calificar_simulacro(s, {}, HOY)
    assert "estimación" in descripcion_estimacion(r, Area.MATEMATICAS).lower()


def test_un_banco_sin_un_area_no_arma_simulacro_completo(banco):
    from icfes.banco import Banco

    sin_ingles = Banco(tuple(p for p in banco.preguntas if p.area is not Area.INGLES))
    with pytest.raises(ValueError, match="no tiene preguntas de"):
        armar_simulacro(sin_ingles, TipoSimulacro.COMPLETO, semilla=1)
