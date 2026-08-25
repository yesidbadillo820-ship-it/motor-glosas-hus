"""El puntaje global es una fórmula oficial: no admite aproximaciones."""

from __future__ import annotations

import pytest

from icfes.dominio import ORDEN_AREAS, Area
from icfes.puntaje import (
    aporte_al_global,
    banda_global,
    brecha_hasta_meta,
    correccion_por_azar,
    correctas_para_puntaje,
    describir_estimacion,
    estimar_puntaje_area,
    indice_global,
    meta_por_area,
    nivel_ingles,
    proporcion_para_puntaje,
    puntaje_global,
    semaforo_area,
)


def _todas(valor):
    return dict.fromkeys(ORDEN_AREAS, valor)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(0, 0), (50, 250), (80, 400), (100, 500)],
)
def test_global_con_el_mismo_puntaje_en_todas_las_areas(valor, esperado):
    assert puntaje_global(_todas(valor)) == esperado


def test_formula_oficial_con_areas_distintas():
    puntajes = {
        Area.LECTURA_CRITICA: 70,
        Area.MATEMATICAS: 60,
        Area.SOCIALES_CIUDADANAS: 65,
        Area.CIENCIAS_NATURALES: 55,
        Area.INGLES: 80,
    }
    esperado = round((3 * 70 + 3 * 60 + 3 * 65 + 3 * 55 + 1 * 80) / 13 * 5)
    assert puntaje_global(puntajes) == esperado


def test_el_indice_global_va_de_0_a_100():
    assert indice_global(_todas(80)) == pytest.approx(80)


def test_falta_un_area_es_un_error_y_no_un_cero_silencioso():
    incompleto = {a: 70 for a in ORDEN_AREAS if a is not Area.INGLES}
    with pytest.raises(ValueError, match="Faltan puntajes"):
        puntaje_global(incompleto)


def test_puntaje_de_area_fuera_de_rango_es_error():
    with pytest.raises(ValueError, match="de 0 a 100"):
        puntaje_global(_todas(140))


def test_un_punto_en_areas_de_peso_3_vale_el_triple_que_en_ingles():
    assert aporte_al_global(Area.MATEMATICAS) == pytest.approx(3 * aporte_al_global(Area.INGLES))
    assert aporte_al_global(Area.MATEMATICAS) == pytest.approx(15 / 13)


def test_la_curva_de_estimacion_es_creciente():
    anterior = -1
    for correctas in range(0, 51):
        actual = estimar_puntaje_area(correctas, 50)
        assert actual >= anterior
        anterior = actual


def test_los_extremos_de_la_estimacion():
    assert estimar_puntaje_area(0, 50) == 0
    assert estimar_puntaje_area(50, 50) == 100


def test_estimacion_sin_preguntas_es_error():
    with pytest.raises(ValueError):
        estimar_puntaje_area(0, 0)


def test_estimacion_con_mas_aciertos_que_preguntas_es_error():
    with pytest.raises(ValueError):
        estimar_puntaje_area(10, 5)


def test_ida_y_vuelta_entre_puntaje_y_proporcion():
    for puntaje in (20, 38, 48, 66, 87):
        proporcion = proporcion_para_puntaje(puntaje)
        assert estimar_puntaje_area(round(proporcion * 1000), 1000) == pytest.approx(puntaje, abs=1)


def test_cuantas_preguntas_hay_que_acertar_para_un_puntaje():
    # Para 80 sobre 100 en Matemáticas (50 preguntas) hacen falta 42.
    assert correctas_para_puntaje(80, 50) == 42
    assert correctas_para_puntaje(100, 50) == 50
    assert correctas_para_puntaje(0, 50) == 0


def test_correccion_por_azar_descuenta_la_suerte():
    # Acertar la cuarta parte es lo que da marcar al azar: dominio real cero.
    assert correccion_por_azar(25, 100) == pytest.approx(0.0)
    assert correccion_por_azar(100, 100) == pytest.approx(1.0)
    assert correccion_por_azar(10, 100) == 0.0


def test_la_estimacion_siempre_se_declara_como_estimacion():
    texto = describir_estimacion(34, 50)
    assert "estimación" in texto.lower()
    assert "no el puntaje oficial" in texto.lower()


@pytest.mark.parametrize(
    ("puntaje", "nivel"),
    [(10, "Pre-A1"), (50, "A1"), (60, "A2"), (75, "B1"), (100, "B1")],
)
def test_niveles_de_ingles(puntaje, nivel):
    assert nivel_ingles(puntaje)[0] == nivel


def test_bandas_del_puntaje_global():
    assert banda_global(255).nombre == "Promedio"
    assert banda_global(410).nombre == "Excepcional"
    assert banda_global(0).nombre == "Bajo"
    assert banda_global(500).nombre == "Excepcional"


def test_semaforo_por_area():
    assert semaforo_area(20)[0] == "crítico"
    assert semaforo_area(45)[0] == "en construcción"
    assert semaforo_area(60)[0] == "sólido"
    assert semaforo_area(90)[0] == "alto"


def test_meta_pareja_cuando_no_hay_diagnostico():
    assert meta_por_area(400) == dict.fromkeys(ORDEN_AREAS, 80)


def test_las_metas_por_area_alcanzan_exactamente_la_meta_global(diagnostico):
    metas = meta_por_area(400, diagnostico)
    assert puntaje_global(dict(metas)) == 400
    assert all(0 <= v <= 100 for v in metas.values())


def test_las_metas_nunca_bajan_del_nivel_actual(diagnostico):
    metas = meta_por_area(400, diagnostico)
    assert all(metas[a] >= diagnostico[a] for a in ORDEN_AREAS)


def test_meta_ya_superada_no_pide_bajar():
    alto = dict.fromkeys(ORDEN_AREAS, 95)
    metas = meta_por_area(300, alto)
    assert all(v == 95 for v in metas.values())


def test_meta_inalcanzable_topa_en_100():
    bajo = dict.fromkeys(ORDEN_AREAS, 10)
    metas = meta_por_area(500, bajo)
    assert all(v == 100 for v in metas.values())


def test_brecha_hasta_la_meta_nunca_es_negativa(diagnostico):
    brechas = brecha_hasta_meta(diagnostico, 400)
    assert all(v >= 0 for v in brechas.values())
