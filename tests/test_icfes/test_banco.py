"""El banco de preguntas es el insumo de todo: si está mal, todo está mal."""

from __future__ import annotations

import json
import re

import pytest

from icfes.banco import (
    ETIQUETA_AL_INICIO,
    MENCION_DE_LETRA,
    BancoInvalido,
    barajar_opciones,
    cargar_banco,
    revisar_banco,
)
from icfes.dominio import AREAS, ORDEN_AREAS, Area


def test_el_banco_del_repositorio_carga_sin_errores(banco):
    assert len(banco) > 0


def test_hay_preguntas_de_las_cinco_areas(banco):
    conteo = banco.conteo_por_area()
    assert all(conteo[a] > 0 for a in ORDEN_AREAS)


def test_todas_las_competencias_tienen_preguntas(banco):
    for nombre_area, competencias in banco.cobertura().items():
        for competencia, cuantas in competencias.items():
            assert cuantas > 0, f"{nombre_area} · {competencia} está sin preguntas"


def test_el_banco_pasa_su_propia_revision_de_calidad(banco):
    assert revisar_banco(banco) == []


def test_ninguna_explicacion_nombra_una_letra_de_opcion(banco):
    # Las opciones se barajan en cada práctica: nombrar "la opción B" mentiría.
    for p in banco.preguntas:
        assert not MENCION_DE_LETRA.search(f"{p.explicacion} {p.trampa}"), p.id


def test_ninguna_opcion_trae_su_letra_escrita_adentro(banco):
    for p in banco.preguntas:
        assert not any(ETIQUETA_AL_INICIO.match(o) for o in p.opciones), p.id


def test_no_hay_ids_repetidos(banco):
    ids = [p.id for p in banco.preguntas]
    assert len(ids) == len(set(ids))


def test_toda_pregunta_explica_y_advierte_la_trampa(banco):
    for p in banco.preguntas:
        assert len(p.explicacion) >= 40, p.id
        assert p.trampa.strip(), p.id


def test_la_respuesta_correcta_se_reparte_entre_las_cuatro_letras(banco):
    # Si el 90 % de las respuestas fueran la B, el banco enseñaría a marcar B.
    for area in ORDEN_AREAS:
        letras = [p.letra_correcta for p in banco.por_area(area)]
        for letra in "ABCD":
            proporcion = letras.count(letra) / len(letras)
            assert 0.1 <= proporcion <= 0.45, f"{AREAS[area].nombre}: letra {letra}"


def test_filtrar_por_area(banco):
    solo_mat = banco.filtrar(area=Area.MATEMATICAS)
    assert solo_mat and all(p.area is Area.MATEMATICAS for p in solo_mat)


def test_filtrar_por_dificultad(banco):
    faciles = banco.filtrar(dificultad_maxima=2)
    assert all(p.dificultad.value <= 2 for p in faciles)


def test_filtrar_excluyendo_ids(banco):
    primeros = {p.id for p in banco.preguntas[:5]}
    resto = banco.filtrar(excluir=primeros)
    assert not (primeros & {p.id for p in resto})


def test_la_muestra_no_repite_preguntas(banco):
    escogidas = banco.muestra(15, area=Area.CIENCIAS_NATURALES, semilla=3)
    assert len({p.id for p in escogidas}) == len(escogidas)


def test_la_muestra_reparte_entre_competencias(banco):
    # Una práctica de 9 preguntas no puede salir toda de la misma competencia.
    escogidas = banco.muestra(9, area=Area.MATEMATICAS, semilla=11)
    assert len({p.competencia for p in escogidas}) >= 2


def test_la_muestra_con_la_misma_semilla_da_lo_mismo(banco):
    a = banco.muestra(8, area=Area.INGLES, semilla=42)
    b = banco.muestra(8, area=Area.INGLES, semilla=42)
    assert [p.id for p in a] == [p.id for p in b]


def test_pedir_mas_preguntas_de_las_que_hay_no_falla(banco):
    escogidas = banco.muestra(10_000, area=Area.LECTURA_CRITICA, semilla=1)
    assert len(escogidas) == len(banco.por_area(Area.LECTURA_CRITICA))


def test_pedir_cero_preguntas_devuelve_vacio(banco):
    assert banco.muestra(0) == ()


def test_buscar_por_id(banco):
    alguna = banco.preguntas[0]
    assert banco.por_id(alguna.id) is alguna
    assert banco.por_id("NO-EXISTE") is None


def test_barajar_mantiene_las_mismas_opciones(banco):
    p = banco.preguntas[0]
    opciones, correcta, orden = barajar_opciones(p, semilla=5)
    assert sorted(opciones) == sorted(p.opciones)
    assert opciones[correcta] == p.opciones[p.correcta]


def test_el_orden_del_barajado_permite_volver_al_indice_original(banco):
    p = banco.preguntas[3]
    _, correcta, orden = barajar_opciones(p, semilla=9)
    assert orden[correcta] == p.correcta


def test_barajar_con_la_misma_semilla_da_el_mismo_orden(banco):
    p = banco.preguntas[1]
    assert barajar_opciones(p, semilla=7) == barajar_opciones(p, semilla=7)


def test_carpeta_inexistente_es_error(tmp_path):
    with pytest.raises(BancoInvalido, match="No existe la carpeta"):
        cargar_banco(tmp_path / "no-existe")


def test_json_mal_escrito_es_error(tmp_path):
    (tmp_path / "malo.json").write_text("{esto no es json", encoding="utf-8")
    with pytest.raises(BancoInvalido, match="mal escrito"):
        cargar_banco(tmp_path)


def test_area_invalida_es_error(tmp_path):
    (tmp_path / "x.json").write_text(
        json.dumps({"area": "astrologia", "preguntas": []}), encoding="utf-8"
    )
    with pytest.raises(BancoInvalido, match="'area'"):
        cargar_banco(tmp_path)


def test_id_repetido_entre_archivos_es_error(tmp_path):
    pregunta = {
        "id": "REP-1",
        "competencia": "Argumentación",
        "componente": "Aleatorio",
        "tema": "t",
        "dificultad": 3,
        "enunciado": "e",
        "opciones": ["a", "b", "c", "d"],
        "correcta": 0,
        "explicacion": "x" * 50,
        "trampa": "y",
    }
    for nombre in ("uno.json", "dos.json"):
        (tmp_path / nombre).write_text(
            json.dumps({"area": "matematicas", "preguntas": [pregunta]}), encoding="utf-8"
        )
    with pytest.raises(BancoInvalido, match="repetido"):
        cargar_banco(tmp_path)


def test_pregunta_sin_campos_obligatorios_es_error(tmp_path):
    (tmp_path / "x.json").write_text(
        json.dumps({"area": "matematicas", "preguntas": [{"id": "A"}]}), encoding="utf-8"
    )
    with pytest.raises(BancoInvalido, match="faltan campos"):
        cargar_banco(tmp_path)


def test_la_revision_detecta_opciones_repetidas(tmp_path):
    pregunta = {
        "id": "D-1",
        "competencia": "Argumentación",
        "componente": "Aleatorio",
        "tema": "t",
        "dificultad": 3,
        "enunciado": "e",
        "opciones": ["igual", "igual", "c", "d"],
        "correcta": 0,
        "explicacion": "x" * 50,
        "trampa": "y",
    }
    (tmp_path / "x.json").write_text(
        json.dumps({"area": "matematicas", "preguntas": [pregunta]}), encoding="utf-8"
    )
    avisos = revisar_banco(cargar_banco(tmp_path))
    assert any("dos opciones iguales" in a for a in avisos)


def test_la_revision_detecta_explicacion_que_nombra_una_letra(tmp_path):
    pregunta = {
        "id": "L-1",
        "competencia": "Argumentación",
        "componente": "Aleatorio",
        "tema": "t",
        "dificultad": 3,
        "enunciado": "e",
        "opciones": ["a", "b", "c", "d"],
        "correcta": 0,
        "explicacion": "La respuesta buena es la opción B por lo que ya se dijo arriba.",
        "trampa": "y",
    }
    (tmp_path / "x.json").write_text(
        json.dumps({"area": "matematicas", "preguntas": [pregunta]}), encoding="utf-8"
    )
    avisos = revisar_banco(cargar_banco(tmp_path))
    assert any("nombra una letra" in a for a in avisos)


def test_los_contextos_con_tabla_estan_bien_formados(banco):
    # Una tabla a medio cerrar se ve rota en la app web.
    for p in banco.preguntas:
        filas = [x for x in p.contexto.splitlines() if x.strip().startswith("|")]
        if filas:
            assert all(x.strip().endswith("|") for x in filas), p.id


def test_no_quedan_marcadores_de_formato_a_medias(banco):
    for p in banco.preguntas:
        texto = f"{p.contexto} {p.enunciado}"
        assert texto.count("**") % 2 == 0, p.id


def test_los_ids_siguen_el_formato_area_numero(banco):
    patron = re.compile(r"^(LC|MAT|SOC|CN|ING)-\d{3}$")
    for p in banco.preguntas:
        assert patron.match(p.id), p.id
