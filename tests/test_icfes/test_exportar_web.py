"""La app web debe salir en un solo archivo y sin JavaScript roto."""

from __future__ import annotations

import json
import re

import pytest

from icfes.exportar_web import MARCA_FIN, MARCA_INICIO, construir_datos, exportar


def _leer_datos(html):
    """Saca el JSON inyectado y lo vuelve a interpretar."""
    inicio = html.index(MARCA_INICIO) + len(MARCA_INICIO)
    fin = html.index(MARCA_FIN)
    return json.loads(html[inicio:fin].replace("<\\/", "</"))


def test_los_datos_traen_todas_las_preguntas(banco):
    datos = construir_datos(banco)
    assert len(datos["preguntas"]) == len(banco)
    assert len(datos["areas"]) == 5


def test_cada_pregunta_lleva_su_explicacion(banco):
    for p in construir_datos(banco)["preguntas"]:
        assert p["explicacion"].strip()
        assert len(p["opciones"]) == 4
        assert 0 <= p["correcta"] <= 3


def test_las_areas_llevan_su_peso_oficial(banco):
    areas = construir_datos(banco)["areas"]
    assert areas["ingles"]["peso"] == 1
    assert areas["matematicas"]["peso"] == 3
    assert areas["ciencias_naturales"]["preguntas"] == 58


def test_sin_configuracion_la_app_arranca_sin_fecha(banco):
    assert construir_datos(banco)["config"] is None


def test_con_configuracion_la_app_arranca_lista(banco, config):
    datos = construir_datos(banco, config)
    assert datos["config"] == {"examen": "2027-08-08", "meta": 400, "horas": 12}


def test_el_archivo_exportado_es_uno_solo(banco, tmp_path):
    ruta = exportar(banco, tmp_path / "app.html")
    assert ruta.is_file()
    assert list(tmp_path.iterdir()) == [ruta]


def test_el_json_inyectado_se_puede_volver_a_leer(banco, tmp_path, config):
    html = exportar(banco, tmp_path / "app.html", config).read_text(encoding="utf-8")
    datos = _leer_datos(html)
    assert len(datos["preguntas"]) == len(banco)
    assert datos["config"]["meta"] == 400


def test_no_queda_el_objeto_por_defecto_pegado_al_json(banco, tmp_path):
    """El bug que rompía la página entera: dos objetos seguidos en el mismo const."""
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    bloque = html[html.index(MARCA_INICIO) + len(MARCA_INICIO) : html.index(MARCA_FIN)]
    # raw_decode consume un objeto; no puede quedar nada después.
    _, fin = json.JSONDecoder().raw_decode(bloque.replace("<\\/", "</"))
    assert bloque[fin:].strip() == ""


def test_las_marcas_aparecen_una_sola_vez(banco, tmp_path):
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    assert html.count(MARCA_INICIO) == 1
    assert html.count(MARCA_FIN) == 1


def test_no_hay_etiquetas_script_sin_escapar_dentro_del_json(banco, tmp_path):
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    # Solo la etiqueta de cierre real del bloque <script> de la plantilla.
    assert html.count("</script>") == 1


def test_la_pagina_es_html_completo(banco, tmp_path):
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    assert html.lstrip().startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert '<html lang="es">' in html


def test_la_pagina_no_pide_nada_por_internet(banco, tmp_path):
    """Si pidiera algo de afuera, dejaría de funcionar sin conexión."""
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    assert not re.search(r'src\s*=\s*["\']https?://', html)
    assert not re.search(r'href\s*=\s*["\']https?://', html)
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html


def test_la_pagina_se_adapta_al_celular(banco, tmp_path):
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    # El espacio después de los dos puntos es opcional en CSS: la prueba no
    # puede depender de cómo se escribió, solo de que la regla exista.
    assert re.search(r"prefers-color-scheme:\s*dark", html)


def test_la_pagina_respeta_el_tema_elegido_por_el_lector(banco, tmp_path):
    """Tres estados: claro, oscuro por sistema y oscuro elegido a mano."""
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    assert re.search(r":root\[data-theme=.dark.\]", html)
    assert re.search(r":root:not\(\[data-theme=.light.\]\)", html)


def test_ningun_color_vive_solo_dentro_de_un_bloque_de_tema(banco, tmp_path):
    """El error clásico: un color definido solo en el bloque oscuro queda sin
    valor cuando el lector no ha elegido tema, y la página sale ilegible."""
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    estilo = html.split("<style>", 1)[1].split("</style>", 1)[0]
    raiz = estilo.split("@media (prefers-color-scheme:dark)")[0]
    base = set(re.findall(r"(--[a-z0-9-]+)\s*:", raiz))
    oscuro = set(re.findall(r"(--[a-z0-9-]+)\s*:", estilo.split(':root[data-theme="dark"]')[1]))
    assert not (oscuro - base), f"tokens sin valor por defecto: {oscuro - base}"


def test_toda_lectura_del_navegador_esta_protegida(banco, tmp_path):
    """localStorage puede fallar (ventana privada): no puede tumbar la app."""
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    for llamada in ("localStorage.getItem", "localStorage.setItem"):
        posicion = html.index(llamada)
        contexto = html[max(0, posicion - 200) : posicion]
        assert "try{" in contexto, llamada


def test_la_curva_de_puntaje_de_la_web_es_la_misma_de_python(banco):
    """La app no reescribe la curva: la recibe exportada desde Python."""
    from icfes.puntaje import CURVA_PUNTAJE

    curva = construir_datos(banco)["escalas"]["curva"]
    assert [tuple(par) for par in curva] == [tuple(par) for par in CURVA_PUNTAJE]


def test_los_niveles_de_ingles_y_el_semaforo_vienen_de_python(banco):
    from icfes.puntaje import NIVELES_INGLES, SEMAFORO_AREA

    escalas = construir_datos(banco)["escalas"]
    assert [tuple(x) for x in escalas["ingles"]] == [tuple(x) for x in NIVELES_INGLES]
    assert [tuple(x) for x in escalas["semaforo"]] == [tuple(x) for x in SEMAFORO_AREA]


def test_la_politica_del_plan_viene_de_python(banco):
    """Las fases y sus mezclas no se reescriben en JavaScript: se exportan.

    Si alguien cambia una proporción en icfes/plan.py, la app cambia con ella.
    """
    from icfes.plan import FASES, MINUTOS_POR_BLOQUE, MINUTOS_SIMULACRO_COMPLETO, PISO_POR_AREA

    plan = construir_datos(banco)["plan"]
    assert plan["minutos_bloque"] == MINUTOS_POR_BLOQUE
    assert plan["minutos_simulacro"] == MINUTOS_SIMULACRO_COMPLETO
    assert plan["piso_area"] == PISO_POR_AREA
    assert [f["nombre"] for f in plan["fases"]] == [f.nombre for f in FASES]
    for exportada, original in zip(plan["fases"], FASES, strict=True):
        assert exportada["proporcion"] == original.proporcion
        assert exportada["objetivo"] == original.objetivo
        assert [tuple(m) for m in exportada["mezcla"]] == [
            (t.value, p) for t, p in original.mezcla.items()
        ]


def test_la_app_trae_todas_las_pantallas(banco, tmp_path):
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    for pantalla in ("vInicio", "vEstudiar", "vSimulacro", "vProgreso", "vPlan", "vAjustes"):
        assert f"function {pantalla}(" in html, f"falta la pantalla {pantalla}"


def test_la_app_avisa_que_los_puntajes_son_estimaciones(banco, tmp_path):
    html = exportar(banco, tmp_path / "app.html").read_text(encoding="utf-8")
    assert "es una estimación" in html
    assert "no son preguntas del examen real" in html.lower() or "No son preguntas" in html


def test_una_plantilla_sin_marcas_es_error(banco, tmp_path):
    mala = tmp_path / "mala.html"
    mala.write_text("<html><body>sin marcas</body></html>", encoding="utf-8")
    with pytest.raises(ValueError, match="marca|MARCA|<DATOS>"):
        exportar(banco, tmp_path / "salida.html", plantilla=mala)


def test_una_plantilla_que_no_existe_es_error(banco, tmp_path):
    with pytest.raises(FileNotFoundError):
        exportar(banco, tmp_path / "salida.html", plantilla=tmp_path / "no-esta.html")


def test_se_crean_las_carpetas_que_falten(banco, tmp_path):
    ruta = exportar(banco, tmp_path / "una" / "otra" / "app.html")
    assert ruta.is_file()


def test_exportar_dos_veces_deja_el_mismo_contenido(banco, tmp_path, config):
    primero = exportar(banco, tmp_path / "a.html", config).read_text(encoding="utf-8")
    segundo = exportar(banco, tmp_path / "b.html", config).read_text(encoding="utf-8")
    assert primero == segundo
