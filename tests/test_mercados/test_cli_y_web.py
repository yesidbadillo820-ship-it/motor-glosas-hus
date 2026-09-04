"""La consola y la aplicación web: que no mientan y que no se caigan."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from mercados import catalogo
from mercados.cli import ADVERTENCIA, construir_parser, main
from mercados.dominio import Vela
from mercados.exportar_web import (
    MANIFEST,
    MARCA_FIN,
    MARCA_INICIO,
    PLANTILLA,
    construir_datos,
    exportar,
)
from mercados.patrones import PATRONES


@pytest.fixture
def velas():
    d = date(2020, 1, 1)
    salida, precio = [], 100.0
    for i in range(400):
        ap = precio * (1 + (0.004 if i % 3 else -0.006))
        ci = ap * (1 + (0.008 if i % 5 else -0.011))
        salida.append(Vela(d + timedelta(days=i), ap, max(ap, ci) * 1.004, min(ap, ci) * 0.996, ci))
        precio = ci
    return salida


@pytest.fixture
def carpeta(tmp_path, velas):
    exportar(tmp_path / "app", velas, titulo="PRUEBA")
    return tmp_path / "app"


# ------------------------------------------------------------------ consola
def test_el_catalogo_esta_completo():
    assert not catalogo.revisar()
    assert len(catalogo.cargar()) == len(PATRONES)


def test_todos_los_comandos_existen():
    validos = set(construir_parser()._subparsers._group_actions[0].choices)
    assert validos == {"patrones", "ficha", "revisar", "vela", "detectar", "medir", "exportar"}


def test_listar_los_patrones(capsys):
    lineas = []
    assert main(["patrones"], salida=lineas.append) == 0
    texto = "\n".join(lineas)
    for p in PATRONES:
        assert p.nombre in texto


def test_la_ficha_dice_que_la_fiabilidad_es_del_autor():
    """Repetir «fiabilidad muy alta» sin decir de quién es sería propaganda."""
    lineas = []
    main(["ficha", "bebe_abandonado_alcista"], salida=lineas.append)
    texto = "\n".join(lineas)
    assert "afirmación del autor" in texto
    assert "sin medición que la respalde" in texto


def test_la_ficha_de_un_patron_inventado_no_finge_saber():
    with pytest.raises(SystemExit, match="No existe"):
        main(["ficha", "vela_magica"], salida=lambda _: None)


def test_la_advertencia_dice_las_tres_cosas_que_importan():
    assert "no predice" in ADVERTENCIA
    assert "pocos casos" in ADVERTENCIA
    assert "comprar o vender" in ADVERTENCIA


def test_medir_termina_siempre_con_la_advertencia(tmp_path, velas):
    csv = tmp_path / "h.csv"
    csv.write_text(
        "Fecha,Apertura,Máximo,Mínimo,Cierre\n"
        + "\n".join(f"{v.fecha},{v.apertura},{v.maximo},{v.minimo},{v.cierre}" for v in velas),
        encoding="utf-8",
    )
    lineas = []
    assert main(["medir", str(csv)], salida=lineas.append) == 0
    assert ADVERTENCIA in "\n".join(lineas)


def test_un_csv_ilegible_da_un_mensaje_y_no_una_traza(tmp_path):
    malo = tmp_path / "malo.csv"
    malo.write_text("hola,mundo\n1,2\n", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main(["detectar", str(malo)], salida=lambda _: None)
    assert "no encuentro la columna" in str(error.value)


# -------------------------------------------------------------- la web app
def test_la_plantilla_trae_las_marcas_de_datos():
    texto = PLANTILLA.read_text(encoding="utf-8")
    assert texto.count(MARCA_INICIO) == 1
    assert texto.count(MARCA_FIN) == 1


def test_los_datos_no_se_pegan_al_objeto_de_ejemplo(carpeta):
    """El fallo del ICFES: sin marca de cierre, el JSON queda pegado y no abre."""
    html = (carpeta / "index.html").read_text(encoding="utf-8")
    trozo = html.split(MARCA_INICIO, 1)[1].split(MARCA_FIN, 1)[0]
    json.loads(trozo)  # revienta si quedó mal pegado


def test_la_app_lleva_los_28_patrones(carpeta):
    html = (carpeta / "index.html").read_text(encoding="utf-8")
    datos = json.loads(html.split(MARCA_INICIO, 1)[1].split(MARCA_FIN, 1)[0])
    assert len(datos["catalogo"]) == len(PATRONES)
    assert datos["medicion"], "la app salió sin medición"


def test_la_app_queda_completa(carpeta):
    nombres = {f.name for f in carpeta.iterdir()}
    assert nombres == {
        "index.html",
        "manifest.webmanifest",
        "sw.js",
        "icono-192.png",
        "icono-512.png",
    }


def test_los_iconos_son_png_de_verdad(carpeta):
    for lado in (192, 512):
        assert (carpeta / f"icono-{lado}.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_el_manifest_apunta_a_archivos_que_existen(carpeta):
    manifest = json.loads((carpeta / "manifest.webmanifest").read_text(encoding="utf-8"))
    for icono in manifest["icons"]:
        assert (carpeta / icono["src"].removeprefix("./")).exists()
    assert MANIFEST["display"] == "standalone"


def test_la_app_avisa_que_no_predice(carpeta):
    html = (carpeta / "index.html").read_text(encoding="utf-8")
    assert "no predice lo que va a pasar" in html
    assert "razón para comprar o vender" in html


def test_el_color_nunca_va_solo(carpeta):
    """Verde/rojo falla la prueba de daltonismo: la forma tiene que decirlo.

    El validador del sistema de gráficas da ΔE 4,1 entre el verde y el rojo
    en visión deutan. Por eso la vela hueca/llena y el símbolo ▲▼ llevan el
    significado, y el color solo acompaña.
    """
    html = (carpeta / "index.html").read_text(encoding="utf-8")
    assert "hueca = cerró subiendo" in html
    assert "llena = cerró bajando" in html
    assert '"▲"' in html and '"▼"' in html


def test_los_datos_traen_lo_que_la_pantalla_necesita(velas):
    datos = construir_datos(velas, "X")
    for clave in (
        "titulo",
        "fuente",
        "horizontes",
        "casosMinimos",
        "resumen",
        "catalogo",
        "medicion",
        "grafico",
        "apariciones",
    ):
        assert clave in datos, f"falta «{clave}» en los datos inyectados"
    assert datos["resumen"]["sesiones"] == len(velas)


def test_el_grafico_no_se_lleva_el_historico_entero(velas):
    """Un CSV de veinte años dentro del HTML lo volvería inabrible en el celular."""
    datos = construir_datos(velas, "X")
    assert len(datos["grafico"]) <= 120


# ------------------------------------------------------- ver la vela dibujada
# Duda razonable del usuario: «el CSV son solo datos, no dice nada de velas».
# Sí lo dice: una vela ES esos cuatro números. El comando lo demuestra.


def test_el_dibujo_marca_los_cuatro_precios():
    from mercados.dibujo import en_texto

    v = Vela(date(2026, 8, 28), 1.1652, 1.1659, 1.1578, 1.1585)
    texto = en_texto(v)
    for etiqueta in ("máximo", "apertura", "cierre", "mínimo"):
        assert etiqueta in texto
    for precio in ("1.16590", "1.16520", "1.15850", "1.15780"):
        assert precio in texto


def test_la_vela_que_sube_va_hueca_y_la_que_baja_llena():
    """La forma lleva el significado; el color no entra en la consola."""
    from mercados.dibujo import en_texto

    sube = Vela(date(2026, 1, 2), 10.0, 11.0, 9.5, 10.8)
    baja = Vela(date(2026, 1, 3), 10.8, 11.0, 9.5, 10.0)
    assert "█" not in en_texto(sube)
    assert "█" in en_texto(baja)


def test_las_medidas_son_las_que_el_libro_pide():
    """«Mecha inferior de al menos dos veces el cuerpo» — la cuenta, hecha."""
    from mercados.dibujo import medidas

    martillo = Vela(date(2026, 1, 2), 10.0, 10.25, 8.0, 10.2)
    texto = "\n".join(medidas(martillo))
    assert "mecha inferior" in texto
    assert "veces el cuerpo" in texto


def test_una_vela_sin_cuerpo_no_divide_por_cero():
    from mercados.dibujo import medidas

    doji = Vela(date(2026, 1, 2), 10.0, 10.5, 9.5, 10.0)
    assert "no tiene cuerpo" in "\n".join(medidas(doji))


def test_el_comando_vela_dice_que_patrones_encajan(tmp_path, velas):
    csv = tmp_path / "h.csv"
    csv.write_text(
        "Fecha,Apertura,Máximo,Mínimo,Cierre\n"
        + "\n".join(f"{v.fecha},{v.apertura},{v.maximo},{v.minimo},{v.cierre}" for v in velas),
        encoding="utf-8",
    )
    lineas = []
    assert main(["vela", str(csv), "--cuantas", "3"], salida=lineas.append) == 0
    texto = "\n".join(lineas)
    assert "cuerpo" in texto and "mecha superior" in texto
    assert "PATRONES QUE ENCAJAN" in texto or "Ningún patrón" in texto


def test_pedir_una_fecha_que_no_esta_lo_dice_con_el_rango(tmp_path, velas):
    csv = tmp_path / "h.csv"
    csv.write_text(
        "Fecha,Apertura,Máximo,Mínimo,Cierre\n"
        + "\n".join(f"{v.fecha},{v.apertura},{v.maximo},{v.minimo},{v.cierre}" for v in velas),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="No hay sesión"):
        main(["vela", str(csv), "--fecha", "1999-01-01"], salida=lambda _: None)
