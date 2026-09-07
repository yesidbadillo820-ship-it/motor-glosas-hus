"""Leer el CSV del bróker sin que un formato raro estropee todo en silencio."""

from __future__ import annotations

from datetime import date

import pytest

from mercados.datos import ArchivoIlegible, leer_fecha, leer_numero, leer_texto


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("1234.56", 1234.56),
        ("1,234.56", 1234.56),  # miles a la inglesa
        ("1.234,56", 1234.56),  # miles a la colombiana
        ("4215,04", 4215.04),  # coma decimal sola
        ('"6.454,22"', 6454.22),
        ("0,5", 0.5),
        ("-12,75", -12.75),
    ],
)
def test_los_dos_formatos_de_numero_dan_lo_mismo(bruto, esperado):
    """Si «1.234,56» entrara como 1,23456, los precios saldrían ×1000."""
    assert leer_numero(bruto) == pytest.approx(esperado)


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("2024-03-15", date(2024, 3, 15)),
        ("15/03/2024", date(2024, 3, 15)),
        ("2024-03-15 00:00:00", date(2024, 3, 15)),
        ("2024-03-15T09:30:00Z", date(2024, 3, 15)),
    ],
)
def test_formatos_de_fecha(bruto, esperado):
    assert leer_fecha(bruto) == esperado


CABECERA_ES = "Fecha;Apertura;Máximo;Mínimo;Cierre\n"
CABECERA_EN = "Date,Open,High,Low,Close\n"


def test_lee_cabecera_en_espanol_con_punto_y_coma():
    velas = leer_texto(CABECERA_ES + "15/03/2024;10,5;11,0;10,0;10,8\n")
    assert len(velas) == 1
    assert velas[0].cierre == pytest.approx(10.8)


def test_lee_cabecera_en_ingles_con_coma():
    velas = leer_texto(CABECERA_EN + "2024-03-15,10.5,11.0,10.0,10.8\n")
    assert velas[0].apertura == pytest.approx(10.5)


def test_ordena_de_la_sesion_mas_vieja_a_la_mas_nueva():
    """Muchas plataformas exportan al revés; sin ordenar, todo sale invertido."""
    texto = CABECERA_EN + "2024-03-17,3,3,3,3\n2024-03-15,1,1,1,1\n2024-03-16,2,2,2,2\n"
    velas = leer_texto(texto)
    assert [v.fecha.day for v in velas] == [15, 16, 17]


def test_una_columna_que_falta_se_dice_con_nombre_propio():
    with pytest.raises(ArchivoIlegible) as error:
        leer_texto("Fecha,Apertura,Cierre\n2024-03-15,1,2\n")
    mensaje = str(error.value)
    assert "maximo" in mensaje and "minimo" in mensaje
    assert "Fecha, Apertura, Cierre" in mensaje  # se muestra lo que sí trae


def test_una_fila_rota_no_tumba_el_archivo_entero():
    texto = CABECERA_EN + "2024-03-15,1,2,0.5,1.5\nbasura,,,,\n2024-03-16,1,2,0.5,1.8\n"
    velas = leer_texto(texto)
    assert len(velas) == 2


def test_si_no_se_puede_leer_ninguna_fila_se_avisa():
    with pytest.raises(ArchivoIlegible, match="ninguna fila"):
        leer_texto(CABECERA_EN + "basura,,,,\n")


def test_una_vela_imposible_se_rechaza():
    """Máximo por debajo del mínimo = archivo malo, no dato raro."""
    velas = leer_texto(CABECERA_EN + "2024-03-15,5,1,9,5\n2024-03-16,1,2,0.5,1.8\n")
    assert len(velas) == 1  # la imposible se descartó, la buena entró


@pytest.mark.parametrize(
    ("precio", "esperado"),
    [
        (4215.04, 2),  # una acción o un índice
        (1.1593, 5),  # EUR/USD: con 2 decimales se borraba el movimiento
        (0.00042, 6),  # una cripto pequeña
        (99.5, 5),
        (100.0, 2),
    ],
)
def test_los_decimales_se_ajustan_al_tamano_del_precio(precio, esperado):
    """Con dos decimales fijos, EUR/USD 1,1593 salía «1,16». Pasó de verdad."""
    from mercados.datos import decimales

    assert decimales(precio) == esperado


def test_el_resumen_de_un_par_de_divisas_no_pierde_el_precio():
    from mercados.datos import resumen

    velas = leer_texto(
        "Fecha,Último,Apertura,Máximo,Mínimo\n"
        '"04.09.2026","1,1593","1,1628","1,1633","1,1585"\n'
        '"03.09.2026","1,1628","1,1589","1,1643","1,1583"\n'
    )
    texto = resumen(velas)
    assert "1.15930" in texto or "1,15930" in texto or "1.1593" in texto


def test_lee_el_formato_de_investing_punto_com():
    """Fecha con puntos, coma decimal, columna «Último» y orden invertido."""
    velas = leer_texto(
        "Fecha,Último,Apertura,Máximo,Mínimo,Vol.,% var.\n"
        '"04.09.2026","1,1593","1,1628","1,1633","1,1585","","-0,30%"\n'
        '"03.09.2026","1,1628","1,1589","1,1643","1,1583","","0,34%"\n'
    )
    assert len(velas) == 2
    assert velas[0].fecha == date(2026, 9, 3)  # ordenado de viejo a nuevo
    assert velas[-1].cierre == pytest.approx(1.1593)
    assert velas[-1].apertura == pytest.approx(1.1628)
