"""El motor de ejercicios: que genere de verdad y que califique bien."""

from __future__ import annotations

import pytest

from noruego.curso import buscar_leccion, todas_las_lecciones
from noruego.dominio import TipoEjercicio as T
from noruego.ejercicios import Ejercicio, acierta, generar, material, normalizar

MINIMO = 6


@pytest.mark.parametrize("clave", [le.clave for _, le, _ in todas_las_lecciones()])
def test_toda_leccion_genera_suficientes_ejercicios(lexico, clave):
    _, leccion = buscar_leccion(clave)
    ejercicios = generar(lexico, leccion, semilla=0)
    assert len(ejercicios) >= MINIMO, f"{clave}: solo {len(ejercicios)}"


def test_toda_leccion_tiene_material(lexico):
    for _, leccion, _ in todas_las_lecciones():
        assert material(lexico, leccion), leccion.clave


def test_los_ejercicios_no_se_repiten_dentro_de_una_leccion(lexico):
    for _, leccion, _ in todas_las_lecciones():
        firmas = [
            (e.tipo, e.fuente, e.enunciado, e.contexto) for e in generar(lexico, leccion, semilla=0)
        ]
        assert len(firmas) == len(set(firmas)), leccion.clave


def test_todo_ejercicio_esta_completo(lexico):
    for _, leccion, _ in todas_las_lecciones():
        for e in generar(lexico, leccion, semilla=1):
            assert e.enunciado.strip(), f"{leccion.clave}/{e.id}"
            assert e.fuente.strip(), f"{leccion.clave}/{e.id}"
            if e.opciones:
                assert len(e.opciones) >= 2, f"{leccion.clave}/{e.id}"
                assert 0 <= e.correcta < len(e.opciones), f"{leccion.clave}/{e.id}"
                assert len(set(e.opciones)) == len(e.opciones), (
                    f"{leccion.clave}/{e.id}: opciones repetidas"
                )
            elif e.escrita:
                assert e.respuesta.strip(), f"{leccion.clave}/{e.id}"
            elif e.tipo is T.ORDENAR:
                assert e.orden, f"{leccion.clave}/{e.id}"


def test_las_opciones_correctas_no_se_delatan(lexico):
    """Si la correcta fuera siempre la más larga, se acertaría sin saber."""
    largas = 0
    total = 0
    for _, leccion, _ in todas_las_lecciones():
        for e in generar(lexico, leccion, semilla=2):
            if len(e.opciones) < 3:
                continue
            total += 1
            if len(e.opciones[e.correcta]) == max(len(o) for o in e.opciones):
                largas += 1
    assert total > 50
    assert largas / total < 0.55, "la respuesta correcta suele ser la más larga"


def test_la_correcta_se_reparte_entre_las_posiciones(lexico):
    from collections import Counter

    posiciones: Counter[int] = Counter()
    for _, leccion, _ in todas_las_lecciones():
        for e in generar(lexico, leccion, semilla=3):
            if len(e.opciones) == 4:
                posiciones[e.correcta] += 1
    total = sum(posiciones.values())
    assert total > 50
    for posicion in range(4):
        assert 0.12 < posiciones[posicion] / total < 0.40, posiciones


def test_ordenar_revuelve_de_verdad(lexico):
    for _, leccion, _ in todas_las_lecciones():
        for e in generar(lexico, leccion, semilla=4):
            if e.tipo is T.ORDENAR and len(e.orden) > 2:
                assert e.datos["revueltas"] != list(e.orden), e.id
                assert sorted(e.datos["revueltas"]) == sorted(e.orden), e.id


def test_generar_con_la_misma_semilla_da_lo_mismo(lexico):
    _, leccion = buscar_leccion("n1")
    a = generar(lexico, leccion, semilla=9)
    b = generar(lexico, leccion, semilla=9)
    assert [e.id for e in a] == [e.id for e in b]
    assert [e.enunciado for e in a] == [e.enunciado for e in b]


def test_semillas_distintas_dan_ejercicios_distintos(lexico):
    _, leccion = buscar_leccion("n1")
    a = {e.enunciado for e in generar(lexico, leccion, semilla=0)}
    b = {e.enunciado for e in generar(lexico, leccion, semilla=1)}
    assert a != b


# --------------------------------------------------------------- calificar --
def test_normalizar_perdona_lo_que_no_es_error():
    assert normalizar("  Hei! ") == normalizar("hei")
    assert normalizar("Jeg bor i Oslo.") == normalizar("jeg bor i oslo")
    assert normalizar("aa") == normalizar("å")


def test_normalizar_conserva_las_letras_noruegas():
    """æ, ø y å no son tildes: cambian la palabra."""
    assert normalizar("søster") != normalizar("soster")
    assert normalizar("være") != normalizar("vaere")


def test_normalizar_quita_las_tildes_del_espanol():
    assert normalizar("qué") == normalizar("que")


def _escrita(respuesta, alternativas=()):
    return Ejercicio(
        id="x",
        tipo=T.TRADUCIR_ES_NO,
        enunciado="e",
        fuente="f",
        respuesta=respuesta,
        alternativas=tuple(alternativas),
    )


def test_acierta_respuesta_escrita():
    e = _escrita("Jeg heter Ana")
    assert acierta(e, "jeg heter ana")
    assert acierta(e, "  Jeg heter Ana.  ")
    assert not acierta(e, "jeg heter ane")


def test_acierta_con_alternativas():
    e = _escrita("carro", ["coche", "auto"])
    assert acierta(e, "coche") and acierta(e, "auto") and acierta(e, "carro")
    assert not acierta(e, "camión")


def test_acierta_opcion_multiple():
    e = Ejercicio(
        id="x", tipo=T.OPCION, enunciado="e", fuente="f", opciones=("a", "b", "c", "d"), correcta=2
    )
    assert acierta(e, 2) and acierta(e, "2")
    assert not acierta(e, 1)
    assert not acierta(e, "no es un número")


def test_acierta_ordenar():
    e = Ejercicio(
        id="x", tipo=T.ORDENAR, enunciado="e", fuente="f", orden=("Jeg", "snakker", "norsk")
    )
    assert acierta(e, "Jeg snakker norsk")
    assert acierta(e, "jeg  snakker   norsk")
    assert not acierta(e, "Snakker jeg norsk")


def test_los_ejercicios_de_genero_solo_ofrecen_los_tres_articulos(lexico):
    for _, leccion, _ in todas_las_lecciones():
        for e in generar(lexico, leccion, semilla=5):
            if e.tipo is T.GENERO:
                assert set(e.opciones) == {"en", "ei", "et"}, e.id


def test_los_ejercicios_de_audio_traen_texto_para_leer(lexico):
    for _, leccion, _ in todas_las_lecciones():
        for e in generar(lexico, leccion, semilla=6):
            if e.tipo.usa_audio:
                assert e.audio.strip(), f"{leccion.clave}/{e.id}"


def test_todo_ejercicio_explica_algo_o_da_pista(lexico):
    sin_ayuda = []
    for _, leccion, _ in todas_las_lecciones():
        for e in generar(lexico, leccion, semilla=7):
            if not e.explicacion.strip() and not e.pista.strip() and e.tipo is not T.PAREJAS:
                sin_ayuda.append(f"{leccion.clave}/{e.id}")
    assert len(sin_ayuda) < 30, sin_ayuda[:10]
