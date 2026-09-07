"""La medición tiene que ser incómoda cuando los datos no dan para más."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from mercados.dominio import Vela
from mercados.medicion import (
    CASOS_MINIMOS,
    Resultado,
    medir_todo,
    tasa_base,
    wilson,
    z_para,
)
from mercados.patrones import POR_CLAVE


def velas_de(cierres: list[float]) -> list[Vela]:
    d = date(2024, 1, 1)
    return [Vela(d + timedelta(days=i), c, c + 0.5, c - 0.5, c) for i, c in enumerate(cierres)]


def test_el_intervalo_se_ensancha_al_hacer_muchas_preguntas():
    """La corrección por comparaciones múltiples: 112 preguntas, no una."""
    una = wilson(20, 30, pruebas=1)
    muchas = wilson(20, 30, pruebas=112)
    assert (muchas[1] - muchas[0]) > (una[1] - una[0])
    assert z_para(112) > z_para(1)


def test_sin_la_correccion_aparecen_hallazgos_falsos():
    """Comprobado con datos aleatorios: sin corregir salían «patrones buenos».

    Con 112 preguntas al 95 %, cerca de seis dan «significativo» por pura
    casualidad. La prueba fija el número: el intervalo corregido tiene que
    abarcar el 50 % en un caso que, sin corregir, lo dejaría fuera.
    """
    # 120 aciertos de 200: el 60 %, con muestra de sobra. Sin corregir el
    # intervalo arranca en 53 % y parece batir a la base del 50 %; corregido
    # arranca en 48 % y la abarca. Es exactamente el falso hallazgo que se
    # veía con datos aleatorios antes de esta corrección.
    sin_corregir = wilson(120, 200, pruebas=1)
    corregido = wilson(120, 200, pruebas=112)
    assert sin_corregir[0] > 0.5, "el caso elegido ya no sirve de ejemplo"
    assert corregido[0] < 0.5


def test_el_intervalo_nunca_se_sale_de_cero_a_uno():
    for aciertos, casos in [(0, 1), (1, 1), (0, 5), (5, 5), (1, 200)]:
        bajo, alto = wilson(aciertos, casos)
        assert 0.0 <= bajo <= alto <= 1.0


def test_la_tasa_base_cuenta_todas_las_sesiones():
    velas = velas_de([1, 2, 3, 4, 5])  # siempre sube
    aciertos, casos = tasa_base(velas, 1, +1)
    assert casos == 4 and aciertos == 4


def test_un_patron_neutro_no_se_mide():
    """El Doji no promete dirección: inventarle una sería inventar."""
    r = Resultado(POR_CLAVE["doji"], 1, 50, 40, 0.0, 25, 50)
    assert not r.medible
    assert "no le atribuye dirección" in r.veredicto


def test_con_pocos_casos_el_veredicto_lo_dice_sin_rodeos():
    r = Resultado(POR_CLAVE["martillo"], 1, 5, 5, 0.02, 250, 500)
    assert "no alcanza para concluir" in r.veredicto
    assert not r.contradice_al_libro, "5 casos no pueden contradecir nada"


def test_un_patron_que_solo_iguala_la_base_no_se_distingue_del_azar():
    r = Resultado(POR_CLAVE["martillo"], 1, 100, 52, 0.001, 250, 500, pruebas=112)
    assert "No se distingue" in r.veredicto


def test_se_marca_lo_que_el_libro_promete_y_los_datos_no_respaldan():
    """El Bebé Abandonado: el libro le da «muy alta». Si no la cumple, se dice."""
    r = Resultado(POR_CLAVE["bebe_abandonado_alcista"], 1, 80, 41, 0.0, 250, 500)
    assert r.contradice_al_libro


def test_no_se_mira_lo_que_todavia_no_paso():
    """Una aparición en la última sesión no tiene futuro que medir."""
    velas = velas_de(list(range(1, 61)))
    for r in medir_todo(velas, [10]):
        assert r.casos <= len(velas) - 10


def test_los_casos_minimos_son_un_numero_declarado():
    assert CASOS_MINIMOS >= 30


@pytest.mark.parametrize("sesiones", [1, 3, 5, 10])
def test_medir_todo_cubre_los_28_patrones(sesiones):
    velas = velas_de([100 + (i % 7) - 3 for i in range(200)])
    resultados = [r for r in medir_todo(velas, [sesiones])]
    assert len({r.patron.clave for r in resultados}) == 28
