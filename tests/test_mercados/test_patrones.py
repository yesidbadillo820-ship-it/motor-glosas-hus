"""Cada uno de los 28 patrones, con un caso de libro construido a mano.

Por qué a mano y no con datos al azar: en 18.000 sesiones simuladas hay
patrones —el Bebé Abandonado, la Triple Formación— que no aparecen ni una vez,
porque exigen huecos completos a ambos lados y eso es rarísimo. Si la única
prueba fueran datos aleatorios, un detector roto y uno correcto se verían
igual: los dos en cero.
"""

from __future__ import annotations

import pathlib
from datetime import date, timedelta

import pytest

from mercados.dominio import Vela
from mercados.patrones import PATRONES, POR_CLAVE, Contexto, buscar

DIA = date(2024, 1, 1)


def vela(indice: int, apertura: float, maximo: float, minimo: float, cierre: float) -> Vela:
    return Vela(DIA + timedelta(days=indice), apertura, maximo, minimo, cierre)


def relleno(cuantas: int, desde: float, paso: float, cuerpo: float = 1.0) -> list[Vela]:
    """Sesiones de fondo: fijan la tendencia previa y el cuerpo promedio.

    `paso` positivo sube (tendencia alcista), negativo baja. El cuerpo es
    constante para que «elefante» (3× el promedio) sea predecible.
    """
    velas = []
    precio = desde
    for i in range(cuantas):
        if paso >= 0:
            ap, ci = precio, precio + cuerpo
        else:
            ap, ci = precio + cuerpo, precio
        velas.append(vela(i, ap, max(ap, ci) + 0.1, min(ap, ci) - 0.1, ci))
        precio += paso
    return velas


def con(fondo: list[Vela], *patron: tuple[float, float, float, float]) -> list[Vela]:
    """Pega las velas del patrón al final del fondo."""
    salida = list(fondo)
    for i, (a, h, low, c) in enumerate(patron):
        salida.append(vela(len(fondo) + i, a, h, low, c))
    return salida


def detecta(clave: str, velas: list[Vela]) -> bool:
    patron = POR_CLAVE[clave]
    contexto = Contexto(velas, fin=len(velas) - 1, largo=patron.velas)
    return patron.detectar(contexto)


# La bajada y la subida de fondo, con cuerpo promedio 1.0.
BAJANDO = relleno(12, 120.0, -1.5)
SUBIENDO = relleno(12, 100.0, +1.5)


# =========================================================== individuales ===
def test_doji_libelula():
    # Sin cuerpo, mecha inferior larguísima, nada arriba, tras caída.
    assert detecta("doji_libelula", con(BAJANDO, (102.0, 102.1, 96.0, 102.0)))


def test_martillo():
    assert detecta("martillo", con(BAJANDO, (102.0, 102.7, 97.0, 102.6)))


def test_el_martillo_no_cuenta_si_el_precio_venia_subiendo():
    """Mismo dibujo tras una subida es un Hombre Colgado, no un martillo."""
    subiendo = con(SUBIENDO, (118.0, 118.7, 113.0, 118.6))
    assert not detecta("martillo", subiendo)
    assert detecta("hombre_colgado", subiendo)


def test_martillo_invertido():
    assert detecta("martillo_invertido", con(BAJANDO, (102.0, 107.0, 101.8, 102.6)))


def test_lapida_doji():
    assert detecta("lapida_doji", con(SUBIENDO, (118.0, 124.0, 117.9, 118.0)))


def test_estrella_fugaz():
    assert detecta("estrella_fugaz", con(SUBIENDO, (118.0, 123.0, 117.8, 118.6)))


def test_marubozu_blanca():
    assert detecta("marubozu_blanca", con(SUBIENDO, (118.0, 121.05, 117.95, 121.0)))


def test_marubozu_negra():
    assert detecta("marubozu_negra", con(BAJANDO, (105.0, 105.05, 101.95, 102.0)))


def test_elefante_verde():
    # Cuerpo 6.0 contra un promedio de 1.0: seis veces, de sobra para 3×.
    assert detecta("elefante_verde", con(SUBIENDO, (118.0, 124.1, 117.9, 124.0)))


def test_elefante_rojo():
    assert detecta("elefante_rojo", con(BAJANDO, (108.0, 108.1, 101.9, 102.0)))


def test_una_vela_grande_no_es_elefante_si_todas_lo_son():
    """«Tres veces el promedio» — con velas grandes de fondo, ya no destaca."""
    fondo = relleno(12, 100.0, +1.5, cuerpo=6.0)
    assert not detecta("elefante_verde", con(fondo, (118.0, 124.1, 117.9, 124.0)))


def test_doji():
    assert detecta("doji", con(SUBIENDO, (118.0, 119.0, 117.0, 118.02)))


def test_el_doji_a_secas_no_se_traga_la_libelula():
    """Contarlos dos veces inflaría cualquier medición."""
    libelula = con(BAJANDO, (102.0, 102.1, 96.0, 102.0))
    assert detecta("doji_libelula", libelula)
    assert not detecta("doji", libelula)


def test_peonza():
    assert detecta("peonza", con(SUBIENDO, (118.0, 119.5, 116.5, 118.4)))


# ============================================================= combinados ===
def test_pauta_penetrante():
    velas = con(
        BAJANDO,
        (108.0, 108.2, 101.8, 102.0),  # roja grande
        (101.0, 106.5, 100.8, 106.0),  # verde: abre bajo el mínimo, cierra sobre la mitad
    )
    assert detecta("pauta_penetrante", velas)


def test_pauta_envolvente_alcista():
    velas = con(BAJANDO, (104.0, 104.2, 102.8, 103.0), (102.5, 105.5, 102.3, 105.0))
    assert detecta("pauta_envolvente_alcista", velas)


def test_la_envolvente_tiene_que_cubrir_TODO_el_cuerpo():
    velas = con(BAJANDO, (104.0, 104.2, 102.8, 103.0), (103.1, 105.5, 103.0, 105.0))
    assert not detecta("pauta_envolvente_alcista", velas)


def test_tres_soldados_blancos():
    velas = con(
        BAJANDO,
        (102.0, 105.2, 101.8, 105.0),
        (103.5, 108.2, 103.3, 108.0),
        (106.0, 111.2, 105.8, 111.0),
    )
    assert detecta("tres_soldados_blancos", velas)


def test_harami_alcista():
    velas = con(BAJANDO, (104.5, 104.7, 101.8, 102.0), (103.0, 103.9, 102.5, 103.5))
    assert detecta("harami_alcista", velas)


def test_tres_estrellas_del_sur():
    velas = con(
        BAJANDO,
        (106.0, 106.0, 99.0, 103.0),  # marubozu abierto, mecha inferior larga
        (104.0, 104.2, 100.0, 102.0),
        (103.0, 103.1, 101.5, 102.2),
    )
    assert detecta("tres_estrellas_del_sur", velas)


def test_estrella_de_la_manana():
    velas = con(
        BAJANDO,
        (108.0, 108.2, 101.8, 102.0),  # elefante rojo
        (100.5, 101.0, 100.0, 100.8),  # peonza con hueco a la baja
        (102.5, 106.0, 102.3, 105.5),  # abre por encima del cuerpo anterior
    )
    assert detecta("estrella_de_la_manana", velas)


def test_bebe_abandonado_alcista():
    """El más raro: la vela del medio queda aislada por huecos a los dos lados."""
    velas = con(
        BAJANDO,
        (108.0, 108.2, 103.0, 103.2),
        (101.0, 101.5, 100.5, 101.0),  # doji, MÁXIMO por debajo del mínimo anterior
        (102.0, 106.0, 101.8, 105.5),  # MÍNIMO por encima del máximo de la doji
    )
    assert detecta("bebe_abandonado_alcista", velas)


def test_toro_180():
    velas = con(BAJANDO, (108.0, 108.2, 101.9, 102.0), (102.0, 108.1, 101.9, 108.0))
    assert detecta("toro_180", velas)


def test_tres_cuervos_negros():
    velas = con(
        SUBIENDO,
        (118.0, 118.2, 114.8, 115.0),
        (116.5, 116.7, 112.0, 112.2),
        (114.0, 114.2, 109.0, 109.2),
    )
    assert detecta("tres_cuervos_negros", velas)


def test_estrella_vespertina():
    velas = con(
        SUBIENDO,
        (114.0, 120.2, 113.8, 120.0),  # verde grande
        (121.0, 122.0, 120.8, 121.4),  # peonza por encima del cuerpo anterior
        (120.5, 120.7, 115.0, 116.0),  # roja que cierra dentro del primer cuerpo
    )
    assert detecta("estrella_vespertina", velas)


def test_bebe_abandonado_bajista():
    velas = con(
        SUBIENDO,
        (114.0, 120.2, 113.8, 120.0),
        (122.0, 122.5, 121.5, 122.0),  # doji con MÍNIMO por encima del máximo previo
        (120.0, 120.2, 115.0, 115.5),  # MÁXIMO por debajo del mínimo de la doji
    )
    assert detecta("bebe_abandonado_bajista", velas)


def test_cubierta_de_la_nube_oscura():
    velas = con(SUBIENDO, (114.0, 120.1, 113.9, 120.0), (121.0, 121.1, 114.9, 115.0))
    assert detecta("cubierta_de_la_nube_oscura", velas)


def test_harami_bajista():
    velas = con(SUBIENDO, (115.5, 118.2, 115.3, 118.0), (116.5, 117.6, 116.0, 117.2))
    assert detecta("harami_bajista", velas)


def test_oso_180():
    velas = con(SUBIENDO, (114.0, 120.1, 113.9, 120.0), (120.0, 120.1, 113.9, 114.0))
    assert detecta("oso_180", velas)


def test_triple_formacion_alcista():
    velas = con(
        SUBIENDO,
        (114.0, 120.1, 113.9, 120.0),  # elefante verde, cuerpo 6
        (119.5, 119.6, 118.4, 118.5),  # tres rojas pequeñas (cuerpo 1 < 6/2)
        (118.8, 118.9, 117.7, 117.8),
        (118.0, 118.1, 116.9, 117.0),
        (117.2, 123.3, 117.1, 123.2),  # otra verde grande
    )
    assert detecta("triple_formacion_alcista", velas)


def test_triple_formacion_bajista():
    velas = con(
        BAJANDO,
        (108.0, 108.1, 101.9, 102.0),  # elefante rojo
        (102.5, 103.6, 102.4, 103.5),  # tres verdes pequeñas
        (103.2, 104.3, 103.1, 104.2),
        (104.0, 105.1, 103.9, 105.0),
        (104.8, 104.9, 98.7, 98.8),  # otra roja grande
    )
    assert detecta("triple_formacion_bajista", velas)


# ================================================================ el motor ===
def test_todos_los_patrones_tienen_su_prueba():
    """Un detector sin caso construido es un detector sin comprobar."""
    # Se mira el texto del archivo, no los nombres de las funciones: el
    # Hombre Colgado se comprueba dentro de la prueba del martillo (son el
    # mismo dibujo con distinta tendencia), y eso vale igual.
    fuente = pathlib.Path(__file__).read_text(encoding="utf-8")
    sin_prueba = [p.clave for p in PATRONES if f'"{p.clave}"' not in fuente]
    assert not sin_prueba, f"patrones sin ninguna prueba: {sin_prueba}"


def test_buscar_no_mira_antes_del_principio():
    """Un patrón de 5 velas no puede detectarse en la sesión número 2."""
    cortas = relleno(3, 100.0, +1.0)
    assert buscar(cortas) is not None  # no revienta
    for aparicion in buscar(cortas):
        assert aparicion.indice - aparicion.patron.velas + 1 >= 0


def test_buscar_devuelve_las_velas_del_patron():
    velas = con(BAJANDO, (108.0, 108.2, 101.9, 102.0), (102.0, 108.1, 101.9, 108.0))
    toros = [a for a in buscar(velas) if a.patron.clave == "toro_180"]
    assert len(toros) == 1
    assert len(toros[0].velas) == 2
    assert toros[0].fecha == velas[-1].fecha


@pytest.mark.parametrize("patron", PATRONES, ids=lambda p: p.clave)
def test_cada_patron_esta_bien_declarado(patron):
    assert patron.velas >= 1
    assert patron.pagina > 0
    assert patron.nombre and patron.clave
