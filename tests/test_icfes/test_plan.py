"""El plan tiene que ser cumplible, no solo bonito."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from icfes.dominio import ORDEN_AREAS, Area
from icfes.plan import (
    FASES,
    MINUTOS_POR_BLOQUE,
    PISO_POR_AREA,
    TipoSesion,
    generar_plan,
    repartir_horas,
)

INICIO = date(2026, 8, 20)
EXAMEN = date(2027, 8, 8)


def _plan(diagnostico, **kw):
    opciones = {"meta_global": 400, "horas_semana": 12, "inicio": INICIO}
    opciones.update(kw)
    return generar_plan(diagnostico, EXAMEN, **opciones)


def test_las_proporciones_de_las_fases_suman_uno():
    assert sum(f.proporcion for f in FASES) == pytest.approx(1.0)


def test_la_mezcla_de_cada_fase_suma_uno():
    for fase in FASES:
        assert sum(fase.mezcla.values()) == pytest.approx(1.0), fase.nombre


def test_el_reparto_de_horas_suma_uno(diagnostico):
    reparto = repartir_horas(diagnostico, 400)
    assert sum(reparto.values()) == pytest.approx(1.0)


def test_ninguna_area_queda_abandonada(diagnostico):
    reparto = repartir_horas(diagnostico, 400)
    assert all(v >= PISO_POR_AREA - 1e-9 for v in reparto.values())


def test_el_area_con_mas_brecha_recibe_mas_tiempo_entre_las_de_igual_peso():
    # Matemáticas y Sociales pesan lo mismo; la más floja debe recibir más.
    diagnostico = {
        Area.LECTURA_CRITICA: 70.0,
        Area.MATEMATICAS: 30.0,
        Area.SOCIALES_CIUDADANAS: 70.0,
        Area.CIENCIAS_NATURALES: 70.0,
        Area.INGLES: 70.0,
    }
    reparto = repartir_horas(diagnostico, 400)
    assert reparto[Area.MATEMATICAS] > reparto[Area.SOCIALES_CIUDADANAS]


def test_ingles_recibe_menos_que_las_areas_de_peso_3_con_igual_brecha():
    parejo = dict.fromkeys(ORDEN_AREAS, 50.0)
    reparto = repartir_horas(parejo, 400)
    assert reparto[Area.INGLES] < reparto[Area.MATEMATICAS]


def test_el_plan_cubre_casi_todo_el_calendario(diagnostico):
    plan = _plan(diagnostico)
    assert plan.semanas_disponibles == (EXAMEN - INICIO).days // 7
    assert plan.semanas[-1].fin < EXAMEN


def test_ningun_bloque_cae_el_dia_del_examen_o_despues(diagnostico):
    plan = _plan(diagnostico)
    for semana in plan.semanas:
        for bloque in semana.bloques:
            assert bloque.fecha < EXAMEN


def test_las_cuatro_fases_aparecen_en_orden(diagnostico):
    plan = _plan(diagnostico)
    vistas = []
    for semana in plan.semanas:
        if semana.fase not in vistas:
            vistas.append(semana.fase)
    assert vistas == [f.nombre for f in FASES]


def test_se_estudia_solo_los_dias_acordados(diagnostico):
    plan = _plan(diagnostico, dias_por_semana=5)
    for semana in plan.semanas:
        dias = {b.fecha for b in semana.bloques if b.tipo is not TipoSesion.SIMULACRO_COMPLETO}
        assert len(dias) <= 5, f"semana {semana.numero}"


def test_la_ultima_semana_afloja_la_carga(diagnostico):
    plan = _plan(diagnostico)
    ultima = plan.semanas[-1]
    tipica = plan.semanas[len(plan.semanas) // 2]
    assert ultima.minutos < tipica.minutos


def test_la_ultima_semana_no_trae_temas_nuevos(diagnostico):
    plan = _plan(diagnostico)
    tipos = {b.tipo for b in plan.semanas[-1].bloques}
    assert TipoSesion.TEORIA not in tipos
    assert tipos <= {TipoSesion.REPASO, TipoSesion.CUADERNO_ERRORES}


def test_hay_simulacros_completos_y_no_en_la_ultima_semana(diagnostico):
    plan = _plan(diagnostico)
    fechas = plan.simulacros_completos()
    assert len(fechas) >= 5
    assert all(f < plan.semanas[-1].inicio for f in fechas)


def test_los_simulacros_alternan_las_dos_sesiones(diagnostico):
    plan = _plan(diagnostico)
    focos = [
        b.foco for s in plan.semanas for b in s.bloques if b.tipo is TipoSesion.SIMULACRO_COMPLETO
    ]
    assert "Sesión 1" in focos and "Sesión 2" in focos


def test_las_horas_semanales_se_respetan(diagnostico):
    plan = _plan(diagnostico, horas_semana=12)
    # Se mira una semana del medio, no la última (que afloja a propósito).
    tipica = plan.semanas[10]
    bloques = [b for b in tipica.bloques if b.tipo is not TipoSesion.SIMULACRO_COMPLETO]
    assert abs(len(bloques) * MINUTOS_POR_BLOQUE / 60 - 12) <= 1


def test_todas_las_areas_aparecen_en_el_plan(diagnostico):
    plan = _plan(diagnostico)
    areas = {b.area for s in plan.semanas for b in s.bloques if b.area}
    assert areas == set(ORDEN_AREAS)


def test_todo_bloque_dice_sobre_que_trabajar(diagnostico):
    plan = _plan(diagnostico)
    for semana in plan.semanas:
        for bloque in semana.bloques:
            assert bloque.foco.strip()
            assert bloque.tipo.instruccion.strip()


def test_los_bloques_de_practica_apuntan_a_una_competencia(diagnostico):
    plan = _plan(diagnostico)
    for semana in plan.semanas:
        for b in semana.bloques:
            if b.tipo is TipoSesion.PRACTICA and b.area:
                assert b.foco in b.area.ficha.competencias


def test_buscar_los_bloques_de_un_dia(diagnostico):
    plan = _plan(diagnostico)
    bloques = plan.bloques_de(INICIO)
    assert bloques and all(b.fecha == INICIO for b in bloques)
    assert plan.bloques_de(EXAMEN + timedelta(days=30)) == ()


def test_buscar_la_semana_de_un_dia(diagnostico):
    plan = _plan(diagnostico)
    assert plan.semana_de(INICIO).numero == 1
    assert plan.semana_de(EXAMEN + timedelta(days=30)) is None


def test_el_resumen_menciona_lo_esencial(diagnostico):
    texto = _plan(diagnostico).resumen()
    for esperado in ("PLAN DE ESTUDIO", "Meta: 400", "Lectura Crítica", "Fundamentos"):
        assert esperado in texto


def test_un_plan_corto_tambien_funciona(diagnostico):
    plan = generar_plan(diagnostico, INICIO + timedelta(days=30), 400, 8, inicio=INICIO)
    assert plan.semanas_disponibles >= 1
    assert {f.nombre for f in FASES} >= {s.fase for s in plan.semanas}


def test_examen_antes_del_inicio_es_error(diagnostico):
    with pytest.raises(ValueError, match="posterior"):
        generar_plan(diagnostico, INICIO - timedelta(days=1), 400, 10, inicio=INICIO)


def test_sin_horas_no_hay_plan(diagnostico):
    with pytest.raises(ValueError, match="al menos una hora"):
        generar_plan(diagnostico, EXAMEN, 400, 0, inicio=INICIO)


def test_dias_por_semana_fuera_de_rango_es_error(diagnostico):
    with pytest.raises(ValueError, match="entre 1 y 7"):
        generar_plan(diagnostico, EXAMEN, 400, 10, inicio=INICIO, dias_por_semana=9)


def test_diagnostico_incompleto_es_error():
    with pytest.raises(ValueError, match="no tiene"):
        generar_plan({Area.MATEMATICAS: 50}, EXAMEN, 400, 10, inicio=INICIO)


def test_sin_fecha_de_inicio_es_error(diagnostico):
    with pytest.raises(ValueError, match="desde qué día"):
        generar_plan(diagnostico, EXAMEN, 400, 10)
