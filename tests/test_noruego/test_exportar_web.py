"""La aplicación tiene que instalarse en el celular y funcionar sin internet."""

from __future__ import annotations

import json
import re

import pytest

from noruego.exportar_web import (
    MANIFEST,
    MARCA_FIN,
    MARCA_INICIO,
    PLANTILLA,
    VARIANTES,
    exportar,
)


@pytest.fixture(scope="module")
def carpeta(tmp_path_factory):
    destino = tmp_path_factory.mktemp("app")
    exportar(destino)
    return destino


@pytest.fixture(scope="module")
def html(carpeta):
    return (carpeta / "index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def datos(html):
    bloque = html[html.index(MARCA_INICIO) + len(MARCA_INICIO) : html.index(MARCA_FIN)]
    return json.loads(bloque.replace("<\\/", "</"))


# ------------------------------------------------------------------ archivos
def test_se_generan_los_archivos_de_la_pwa(carpeta):
    nombres = {f.name for f in carpeta.iterdir()}
    assert {
        "index.html",
        "manifest.webmanifest",
        "sw.js",
        "icono-192.png",
        "icono-512.png",
    } <= nombres


def test_el_manifest_es_valido(carpeta):
    m = json.loads((carpeta / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert m["name"] and m["short_name"]
    assert m["display"] == "standalone"
    assert m["start_url"].endswith("index.html")
    assert len(m["icons"]) >= 2
    for icono in m["icons"]:
        assert (carpeta / icono["src"].lstrip("./")).is_file()


def test_los_iconos_son_png_de_verdad(carpeta):
    for lado in (192, 512):
        crudo = (carpeta / f"icono-{lado}.png").read_bytes()
        assert crudo.startswith(b"\x89PNG\r\n\x1a\n"), "no es un PNG"
        assert len(crudo) > 100


def test_el_service_worker_guarda_la_aplicacion(carpeta):
    sw = (carpeta / "sw.js").read_text(encoding="utf-8")
    assert "caches.open" in sw and "addAll" in sw
    assert "index.html" in sw
    assert "__VERSION__" not in sw, "quedó sin reemplazar la versión"


def test_la_pagina_es_html_completo(html):
    assert html.lstrip().startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert '<html lang="es">' in html


def test_la_pagina_esta_pensada_para_el_celular(html):
    assert 'name="viewport"' in html
    assert "viewport-fit=cover" in html
    assert 'rel="manifest"' in html
    assert "apple-mobile-web-app-capable" in html
    assert "safe-area-inset" in html, "no respeta la zona segura del iPhone"


def test_los_botones_son_grandes_para_el_dedo(html):
    """Un botón por debajo de 44 px es difícil de tocar en un celular."""
    toque = re.search(r"--toque:\s*(\d+)px", html)
    assert toque and int(toque.group(1)) >= 44


def test_la_pagina_no_pide_nada_por_internet(html):
    assert not re.search(r'src\s*=\s*["\']https?://', html)
    assert not re.search(r'href\s*=\s*["\']https?://', html)
    assert "fetch(" not in html.split("<script>")[1]
    assert "XMLHttpRequest" not in html


def test_los_tres_estados_de_tema_estan_definidos(html):
    assert re.search(r"prefers-color-scheme:\s*dark", html)
    assert re.search(r":root\[data-theme=.dark.\]", html)
    assert re.search(r":root:not\(\[data-theme=.light.\]\)", html)


def test_ningun_color_vive_solo_en_el_bloque_oscuro(html):
    estilo = html.split("<style>", 1)[1].split("</style>", 1)[0]
    raiz = estilo.split("@media (prefers-color-scheme:dark)")[0]
    base = set(re.findall(r"(--[a-z0-9-]+)\s*:", raiz))
    oscuro = set(re.findall(r"(--[a-z0-9-]+)\s*:", estilo.split(':root[data-theme="dark"]')[1]))
    assert not (oscuro - base), f"tokens sin valor por defecto: {oscuro - base}"


def test_toda_lectura_del_navegador_esta_protegida(html):
    for llamada in ("localStorage.getItem", "localStorage.setItem"):
        posicion = html.index(llamada)
        assert "try{" in html[max(0, posicion - 200) : posicion], llamada


def test_solo_hay_una_etiqueta_de_cierre_de_script(html):
    assert html.count("</script>") == 1


def test_las_marcas_de_datos_aparecen_una_sola_vez(html):
    assert html.count(MARCA_INICIO) == 1
    assert html.count(MARCA_FIN) == 1


def test_no_queda_el_objeto_por_defecto_pegado_al_json(html):
    bloque = html[html.index(MARCA_INICIO) + len(MARCA_INICIO) : html.index(MARCA_FIN)]
    _, fin = json.JSONDecoder().raw_decode(bloque.replace("<\\/", "</"))
    assert bloque[fin:].strip() == ""


# --------------------------------------------------------------------- datos
def test_el_curso_completo_viaja_dentro(datos):
    assert len(datos["lecciones"]) >= 20
    assert len(datos["modulos"]) >= 10
    assert datos["lexico"]["sustantivos"]


def test_cada_leccion_trae_varias_variantes(datos):
    for leccion in datos["lecciones"]:
        assert leccion["variantes"], leccion["clave"]
        assert len(leccion["variantes"]) <= VARIANTES
        for variante in leccion["variantes"]:
            assert len(variante) >= 6, leccion["clave"]


def test_todo_ejercicio_exportado_es_usable(datos):
    for leccion in datos["lecciones"]:
        for variante in leccion["variantes"]:
            for e in variante:
                assert e["enunciado"] and e["tipo"] and e["fuente"]
                if "opciones" in e:
                    assert 0 <= e["correcta"] < len(e["opciones"])


def test_las_lecciones_van_en_orden(datos):
    indices = [le["indice"] for le in datos["lecciones"]]
    assert indices == sorted(indices)


def test_cada_leccion_pertenece_a_un_modulo_que_existe(datos):
    claves = {m["clave"] for m in datos["modulos"]}
    for leccion in datos["lecciones"]:
        assert leccion["modulo"] in claves


def test_cada_modulo_lista_lecciones_que_existen(datos):
    claves = {le["clave"] for le in datos["lecciones"]}
    for modulo in datos["modulos"]:
        for clave in modulo["lecciones"]:
            assert clave in claves


def test_la_voz_pedida_es_noruega(datos):
    assert datos["idiomaVoz"].startswith("nb")


def test_las_reglas_del_juego_viajan(datos):
    for campo in ("xpAcierto", "xpLeccion", "xpPerfecta", "vidas"):
        assert datos["juego"][campo] > 0


def test_la_aplicacion_declara_que_ensena_bokmal(html):
    assert "bokmål" in html.lower()


def test_la_aplicacion_avisa_que_la_pronunciacion_es_aproximada(html):
    assert "aproxima" in html.lower()


def test_plantilla_sin_marcas_es_error(tmp_path):
    mala = tmp_path / "mala.html"
    mala.write_text("<html></html>", encoding="utf-8")
    with pytest.raises(ValueError):
        exportar(tmp_path / "salida", plantilla=mala)


def test_plantilla_inexistente_es_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        exportar(tmp_path / "salida", plantilla=tmp_path / "no-esta.html")


def test_exportar_dos_veces_da_lo_mismo(tmp_path):
    a = exportar(tmp_path / "a").read_text(encoding="utf-8")
    b = exportar(tmp_path / "b").read_text(encoding="utf-8")
    assert a == b


def test_la_plantilla_del_repositorio_existe():
    assert PLANTILLA.is_file()
    assert MANIFEST["lang"] == "es"


# --- La voz noruega --------------------------------------------------------
# En la prueba real, la app dijo «este dispositivo no tiene voz noruega» y no
# ofrecía ninguna salida: el usuario no sabía que eso se instala en Windows.


def test_la_busqueda_de_voz_acepta_las_tres_etiquetas_del_noruego():
    """Los sistemas la etiquetan «nb», «no» o «nn» según el fabricante."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    for etiqueta in ("nb", "no", "nn"):
        assert f'startsWith("{etiqueta}")' in plantilla, f"no se busca la voz «{etiqueta}»"


def test_la_pantalla_se_redibuja_cuando_las_voces_llegan_tarde():
    """Chrome entrega las voces después de cargar: sin esto el aviso miente."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    bloque = plantilla.split("onvoiceschanged", 1)[1][:600]
    assert "pintar()" in bloque, "al llegar las voces no se vuelve a dibujar la pantalla"
    assert "antes !== !!VOZ" in bloque, "se redibuja siempre, no solo cuando cambia"
    assert "escribiendo" in bloque, "un redibujado podría borrar lo que el usuario escribe"


def test_se_dice_como_instalar_la_voz_en_cada_sistema():
    """Windows faltaba: el aviso solo hablaba de Android y de iPhone."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    assert "function comoInstalarVoz()" in plantilla
    for sistema in ("Android", "iPhone", "Windows", "Mac"):
        assert sistema in plantilla, f"no se explica cómo instalar la voz en {sistema}"


def test_los_tres_avisos_de_audio_apagado_dicen_como_arreglarlo():
    """Un aviso sin salida deja al usuario atascado, que fue lo que pasó."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    assert plantilla.count("comoInstalarVoz()") >= 4, (
        "algún aviso de «no hay voz» no dice cómo instalarla"
    )


def test_windows_avisa_del_bloqueo_del_servidor_del_hospital():
    """El PC de cartera falló con «No se pudo instalar el paquete de voz».

    Es un equipo de dominio: las actualizaciones pasan por el servidor de
    Sistemas, que bloquea los paquetes opcionales. Sin este aviso, el usuario
    cree que hizo algo mal y sigue intentando.
    """
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    tramo = plantilla.split("/Windows/i.test(ua)", 1)[1][:700]
    assert "No se pudo instalar el paquete de voz" in tramo, (
        "no se nombra el error exacto que muestra Windows"
    )
    assert "celular" in tramo, "no se ofrece la salida que sí funciona"


# --- El audio automático ---------------------------------------------------
# Fallo real del 31-08: en «escucha y elige» la palabra NO sonaba al aparecer,
# solo al pulsar «Comprobar». El mecanismo existía —`tras()` buscaba un
# atributo `data-autoaudio`— pero NINGÚN ejercicio lo ponía: era código muerto.


def test_el_ejercicio_de_escucha_suena_solo_al_aparecer():
    """Sin esto, «escucha y elige» se convierte en «lee y elige»."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    cuerpo = plantilla.split("function audioGrande(", 1)[1].split("\n}", 1)[0]
    assert "data-autoaudio=" in cuerpo, (
        "audioGrande no marca el audio para que suene solo: `tras()` no encontrará nada"
    )


def test_el_audio_no_se_repite_al_tocar_cada_opcion():
    """Tocar una opción vuelve a pintar la pantalla entera."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    assert "data-audio-clave=" in plantilla, "falta la marca que evita repetir la palabra"
    tras = plantilla.split("function tras()", 1)[1].split("\n}", 1)[0]
    assert "ULTIMO_AUDIO" in tras, "tras() no recuerda qué dijo: repetiría en cada toque"
    assert "clave === ULTIMO_AUDIO" in tras, "tras() no compara antes de volver a hablar"


def test_no_habla_dos_veces_al_revelar_la_respuesta():
    """`comprobar()` ya dice la palabra al acertar: repetirla sonaría encima."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    cuerpo = plantilla.split("function audioGrande(", 1)[1].split("\n}", 1)[0]
    assert "!s.mostrando" in cuerpo, (
        "el audio automático sigue activo con la respuesta revelada: sonaría doble"
    )


def test_los_tres_ejercicios_de_oido_usan_el_mismo_camino():
    """escuchar_opcion, escuchar_escribir y pronunciar: todos por audioGrande."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    assert plantilla.count("audioGrande(") >= 4, (
        "algún ejercicio de oído arma su botón por su cuenta y se queda sin audio automático"
    )


# --- Los botones que hablan ------------------------------------------------
# Fallo real del 31-08, y el peor de todos: TODOS los botones 🔊 estaban mudos.
# `JSON.stringify` devuelve el texto entre comillas dobles y el atributo HTML
# también va entre comillas dobles, así que el navegador leía
#     onclick="decir("gå")"
# y lo cortaba en la primera comilla: el atributo quedaba en «decir(» y el
# botón no hacía nada. Solo hablaban el audio automático (va por un atributo
# de datos) y el de acertar (se llama desde JavaScript) — por eso costó verlo.

MANEJADOR_ROTO = re.compile(r'onclick="[^"]*\$\{JSON\.stringify')


def test_ningun_manejador_mete_comillas_dobles_en_un_atributo():
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    rotos = MANEJADOR_ROTO.findall(plantilla)
    assert not rotos, (
        "un onclick con JSON.stringify sin escapar: el navegador corta el "
        f"atributo en la primera comilla y el botón queda mudo ({len(rotos)})"
    )


def test_todos_los_botones_que_hablan_salen_del_mismo_ayudante():
    """Una sola puerta: si alguien arma el onclick a mano, vuelve el fallo."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    assert "function alPulsarDecir(" in plantilla
    assert plantilla.count("alPulsarDecir(") >= 14, (
        "algún botón de audio arma su propio onclick en vez de usar el ayudante"
    )


def test_el_ayudante_escapa_para_html():
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    cuerpo = plantilla.split("function alPulsarDecir(", 1)[1].split("\n}", 1)[0]
    assert "esc(js)" in cuerpo, "el ayudante no escapa el JavaScript para el atributo"
