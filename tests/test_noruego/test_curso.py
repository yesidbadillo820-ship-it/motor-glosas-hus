"""El curso tiene que ser una ruta que se pueda recorrer de principio a fin."""

from __future__ import annotations

from collections import Counter

from noruego.curso import MODULOS, buscar_leccion, todas_las_lecciones, total_lecciones
from noruego.dominio import Nivel, TipoEjercicio


def test_el_curso_tiene_al_menos_veinte_lecciones():
    assert total_lecciones() >= 20


def test_las_claves_de_leccion_no_se_repiten():
    claves = [le.clave for _, le, _ in todas_las_lecciones()]
    assert [k for k, c in Counter(claves).items() if c > 1] == []


def test_las_claves_de_modulo_no_se_repiten():
    claves = [m.clave for m in MODULOS]
    assert [k for k, c in Counter(claves).items() if c > 1] == []


def test_los_indices_son_consecutivos():
    indices = [i for _, _, i in todas_las_lecciones()]
    assert indices == list(range(len(indices)))


def test_el_curso_empieza_desde_cero():
    primer_modulo = MODULOS[0]
    assert primer_modulo.nivel is Nivel.CERO


def test_los_niveles_no_retroceden():
    """Un curso que salta de A2 a A1 confunde. El orden tiene que subir."""
    vistos = [m.nivel.orden for m in MODULOS]
    assert vistos == sorted(vistos)


def test_el_curso_llega_al_menos_hasta_b2():
    assert max(m.nivel.orden for m in MODULOS) >= Nivel.B2.orden


def test_todo_modulo_tiene_lecciones():
    for m in MODULOS:
        assert m.lecciones, m.clave


def test_toda_leccion_declara_objetivo_y_tipos():
    for _modulo, leccion, _ in todas_las_lecciones():
        assert leccion.titulo.strip(), leccion.clave
        assert leccion.objetivo.strip(), leccion.clave
        assert leccion.tipos, leccion.clave
        for tipo in leccion.tipos:
            assert isinstance(tipo, TipoEjercicio)


def test_toda_leccion_pide_una_cantidad_razonable():
    for _, leccion, _ in todas_las_lecciones():
        assert 6 <= leccion.ejercicios <= 20, leccion.clave


def test_las_fuentes_son_tuplas_no_cadenas():
    """`fuentes=("frases")` es una cadena, y al recorrerla da letras sueltas."""
    for _, leccion, _ in todas_las_lecciones():
        assert isinstance(leccion.fuentes, tuple), leccion.clave
        for fuente in leccion.fuentes:
            assert len(fuente) > 1, f"{leccion.clave}: «{fuente}» parece una letra suelta"


def test_las_lecciones_con_dialogo_apuntan_a_uno_que_existe(lexico):
    ids = {d["id"] for d in lexico.dialogos}
    for _, leccion, _ in todas_las_lecciones():
        if leccion.dialogo:
            assert leccion.dialogo in ids, leccion.clave


def test_las_reglas_de_gramatica_citadas_existen(lexico):
    claves = {g["clave"] for g in lexico.gramatica}
    for _, leccion, _ in todas_las_lecciones():
        for clave in leccion.gramatica:
            assert clave in claves, f"{leccion.clave} cita «{clave}», que no existe"


def test_los_sonidos_citados_existen(lexico):
    ids = {s["id"] for s in lexico.sonidos}
    for _, leccion, _ in todas_las_lecciones():
        for identificador in leccion.sonidos:
            assert identificador in ids, f"{leccion.clave} cita «{identificador}»"


def test_los_temas_citados_existen():
    from noruego.dominio import TEMAS_POR_CLAVE

    for _, leccion, _ in todas_las_lecciones():
        for tema in leccion.temas:
            assert tema in TEMAS_POR_CLAVE, f"{leccion.clave}: tema «{tema}»"


def test_buscar_leccion():
    modulo, leccion = buscar_leccion("s1")
    assert leccion.clave == "s1"
    assert modulo.clave == "sonidos"
    assert buscar_leccion("no-existe") is None
