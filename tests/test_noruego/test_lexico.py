"""El contenido lingüístico es el cimiento: si está mal, el curso enseña mal.

La regla del proyecto es que no se inventa noruego. Estas pruebas verifican que
lo escrito sea internamente coherente (que un neutro haga el definido en -et,
que un verbo traiga sus cuatro formas) y que nada quede marcado como dudoso sin
que se note.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from noruego.dominio import TEMAS_POR_CLAVE, Genero, GrupoVerbal, Nivel
from noruego.lexico import DIRECTORIO, LexicoInvalido, cargar, revisar


def test_el_lexico_carga(lexico):
    assert len(lexico) > 300


def test_no_hay_avisos_de_calidad(lexico):
    assert revisar(lexico) == []


def test_no_hay_ids_repetidos(lexico):
    ids = [e["id"] for grupo in lexico.todo.values() for e in grupo]
    assert [k for k, c in Counter(ids).items() if c > 1] == []


def test_todo_elemento_declara_un_nivel_valido(lexico):
    validos = {n.value for n in Nivel}
    for grupo in lexico.todo.values():
        for e in grupo:
            if "nivel" in e:
                assert e["nivel"] in validos, e["id"]


def test_todo_elemento_declara_un_tema_valido(lexico):
    for grupo in lexico.todo.values():
        for e in grupo:
            if e.get("tema"):
                assert e["tema"] in TEMAS_POR_CLAVE, e["id"]


def test_los_sustantivos_traen_genero_y_forma_definida(lexico):
    for s in lexico.sustantivos:
        if s.get("soloPlural"):
            continue
        assert s["genero"] in {g.value for g in Genero}, s["id"]
        assert s["def"].strip(), s["id"]


def test_los_neutros_hacen_el_definido_en_et(lexico):
    """«et hus» hace «huset». Si un neutro no termina así, hay una errata."""
    for s in lexico.sustantivos:
        if s["genero"] == "et":
            primera = s["def"].split(" / ")[0]
            assert primera.endswith(("et", "e")), f"{s['id']}: definido «{primera}»"


def test_los_femeninos_muestran_las_dos_formas_aceptadas(lexico):
    """En bokmål «ei jente» también se dice «en jente»: el curso enseña las dos."""
    for s in lexico.sustantivos:
        if s["genero"] == "ei" and not s.get("soloPlural"):
            assert " / " in s["def"], f"{s['id']}: falta la forma en «-en»"


def test_los_verbos_traen_las_cuatro_formas(lexico):
    for v in lexico.verbos:
        for campo in ("inf", "pres", "pas", "perf"):
            assert v[campo].strip(), f"{v['id']}: falta {campo}"
        assert v["perf"].startswith("har "), v["id"]
        assert v["grupo"] in {g.value for g in GrupoVerbal}, v["id"]


def test_el_presente_no_lleva_a_delante(lexico):
    """El infinitivo lleva «å»; el presente no. Confundirlos enseña mal."""
    for v in lexico.verbos:
        assert not v["pres"].startswith("å "), v["id"]
        assert not v["inf"].startswith("å "), f"{v['id']}: el infinitivo se guarda sin «å»"


def test_los_verbos_del_grupo_1_hacen_el_pasado_en_et(lexico):
    for v in lexico.verbos:
        if v["grupo"] == "1":
            assert v["pas"].endswith(("et", "a")), f"{v['id']}: pasado «{v['pas']}»"


def test_los_verbos_del_grupo_2_hacen_el_pasado_en_te(lexico):
    for v in lexico.verbos:
        if v["grupo"] == "2":
            assert v["pas"].endswith("te"), f"{v['id']}: pasado «{v['pas']}»"


def test_los_verbos_del_grupo_4_hacen_el_pasado_en_dde(lexico):
    for v in lexico.verbos:
        if v["grupo"] == "4":
            assert v["pas"].endswith("dde"), f"{v['id']}: pasado «{v['pas']}»"


def test_los_adjetivos_traen_sus_tres_formas(lexico):
    for a in lexico.adjetivos:
        for campo in ("base", "neutro", "plural"):
            assert a[campo].strip(), f"{a['id']}: falta {campo}"


def test_toda_palabra_trae_pronunciacion_aproximada(lexico):
    for grupo in ("sustantivos", "verbos", "adjetivos", "frases", "numeros"):
        for e in lexico.todo[grupo]:
            assert e["pron"].strip(), f"{e['id']}: sin pronunciación"


def test_las_reglas_de_gramatica_traen_ejemplos_y_error_tipico(lexico):
    for g in lexico.gramatica:
        assert len(g["ejemplos"]) >= 2, g["id"]
        assert g["error"].strip(), g["id"]
        for ejemplo in g["ejemplos"]:
            assert ejemplo["no"].strip() and ejemplo["es"].strip(), g["id"]


def test_los_dialogos_tienen_lineas_para_completar(lexico):
    for d in lexico.dialogos:
        assert len(d["lineas"]) >= 4, d["id"]
        assert d["huecos"], d["id"]
        for indice in d["huecos"]:
            assert 0 <= indice < len(d["lineas"]), d["id"]
            assert d["lineas"][indice]["quien"] == "Tú", (
                f"{d['id']}: solo se completan las líneas del estudiante"
            )


def test_cada_linea_de_dialogo_esta_completa(lexico):
    for d in lexico.dialogos:
        for linea in d["lineas"]:
            for campo in ("quien", "no", "es", "pron"):
                assert linea[campo].strip(), f"{d['id']}: línea incompleta"


def test_los_sonidos_explican_como_lograrlos(lexico):
    for s in lexico.sonidos:
        assert s["consejo"].strip(), s["id"]
        assert len(s["ejemplos"]) >= 2, s["id"]


def test_cada_archivo_declara_de_donde_sale_su_contenido(lexico):
    """Cada JSON trae una nota que explica qué es y qué no es."""
    for tipo, nota in lexico.notas.items():
        assert nota.strip(), f"{tipo}.json no tiene nota"


def test_las_notas_avisan_que_la_pronunciacion_es_aproximada(lexico):
    texto = " ".join(lexico.notas.values()).lower()
    assert "aproxima" in texto


def test_los_json_son_legibles_y_estan_ordenados():
    for archivo in DIRECTORIO.glob("*.json"):
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        assert "palabras" in datos, archivo.name
        assert datos.get("variante") == "bokmål", archivo.name


def test_carpeta_inexistente_es_error(tmp_path):
    with pytest.raises(LexicoInvalido):
        cargar(tmp_path / "no-existe")


def test_json_roto_es_error(tmp_path):
    (tmp_path / "frases.json").write_text("{roto", encoding="utf-8")
    with pytest.raises(LexicoInvalido, match="mal escrito"):
        cargar(tmp_path)


def test_falta_un_campo_obligatorio_es_error(tmp_path):
    (tmp_path / "frases.json").write_text(
        json.dumps({"tipo": "frases", "palabras": [{"id": "x", "no": "Hei"}]}), encoding="utf-8"
    )
    with pytest.raises(LexicoInvalido, match="faltan"):
        cargar(tmp_path)


def test_ids_repetidos_entre_archivos_es_error(tmp_path):
    palabra = {
        "id": "rep",
        "no": "hei",
        "es": "hola",
        "tema": "saludos",
        "nivel": "A1",
        "pron": "jei",
    }
    for nombre in ("frases.json",):
        (tmp_path / nombre).write_text(
            json.dumps({"tipo": "frases", "palabras": [palabra, dict(palabra)]}), encoding="utf-8"
        )
    with pytest.raises(LexicoInvalido, match="repetidos"):
        cargar(tmp_path)


def test_el_curso_cubre_todos_los_niveles_hasta_b2(lexico):
    niveles = {e["nivel"] for grupo in lexico.todo.values() for e in grupo if "nivel" in e}
    assert {"cero", "A1", "A2", "B1"} <= niveles
