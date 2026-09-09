"""No se le puede atribuir a la IA una decisión que la IA no tomó.

09-09-2026, caso 4 de la prueba del auditor. En una glosa RATIFICADA el
motor no llama a la IA: devuelve el texto fijo que definió el área y marca
el dictamen con `modelo_ia = "texto_fijo"`. La acción (DEFENDER 100%) sale
de una tabla escrita en Python, no de un análisis.

Y aun así la pantalla remataba el dictamen con un recuadro verde que decía:

    💡 La IA recomienda · DEFENDER 100%
    «La IA recomienda defender íntegramente la glosa.»

Para el auditor eso es una segunda opinión que respalda la primera. No
existe: es la misma regla dicha dos veces, y la segunda con la autoridad
prestada de algo que nunca corrió. Es exactamente la clase de afirmación
sin respaldo que el motor tiene prohibido hacer en el papel que se radica;
no puede permitírsela en la pantalla.

QUÉ CUIDA ESTA PRUEBA. Que el recuadro diga de dónde salió de verdad la
decisión: de la IA cuando la IA corrió, y de la regla fija del área cuando
el dictamen es texto fijo, abstención, plantilla o el argumento que dictó
el propio auditor.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"

# Los caminos del motor en los que el dictamen NO lo escribió la IA.
# Son los valores que `glosa_service` le pone a `modelo_ia`.
SIN_IA = ("texto_fijo", "plantilla", "abstencion", "directo_auditor")


def _pagina() -> str:
    return INDEX.read_text(encoding="utf-8")


def _funcion(nombre: str, texto: str) -> str:
    ini = texto.index(f"function {nombre}(")
    sig = texto.find("\nfunction ", ini + 1)
    return texto[ini : sig if sig != -1 else ini + 4000]


def test_el_recuadro_mira_quien_escribio_el_dictamen():
    cuerpo = _funcion("renderAccionIA", _pagina())
    assert "modelo_ia" in cuerpo or "_dictamenLoEscribioLaIA" in cuerpo, (
        "El recuadro de la recomendación no mira `modelo_ia`: le atribuye a la IA "
        "hasta las decisiones que la IA no tomó (ratificación, extemporánea, "
        "abstención, argumento dictado por el auditor)."
    )


def test_estan_listados_todos_los_caminos_sin_ia():
    pagina = _pagina()
    ini = pagina.index("var _SIN_IA = [")
    lista = pagina[ini : pagina.index("]", ini)]
    for camino in SIN_IA:
        assert camino in lista, (
            f"Falta «{camino}» en la lista de caminos sin IA. `glosa_service` le pone "
            f"ese valor a `modelo_ia` cuando la IA no corrió, así que ese dictamen "
            f"seguiría saliendo con «La IA recomienda»."
        )


def test_los_textos_del_recuadro_no_dicen_la_ia_a_secas():
    """Ninguna de las cuatro frases puede afirmar la autoría antes de saberla."""
    cuerpo = _funcion("renderAccionIA", _pagina())
    for linea in cuerpo.splitlines():
        if "texto:" not in linea:
            continue
        assert "'La IA" not in linea and '"La IA' not in linea, (
            "Esta frase le atribuye la decisión a la IA sin mirar si la IA corrió:\n"
            f"    {linea.strip()}\n"
            "Tiene que salir de la variable que dice quién decidió de verdad."
        )


def test_el_titulo_tampoco_esta_escrito_a_mano():
    cuerpo = _funcion("renderAccionIA", _pagina())
    assert "'💡 La IA recomienda · '" not in cuerpo, (
        "El título del recuadro sigue fijo en «💡 La IA recomienda», así que sale "
        "igual en las ratificaciones, donde la IA no corrió."
    )
    assert "titulo" in cuerpo, "El título del recuadro no se calcula."


def test_el_camino_de_la_ia_sigue_diciendo_que_es_de_la_ia():
    """La corrección no puede borrar la atribución cuando SÍ es de la IA:
    el auditor necesita saber cuándo lo que lee es un análisis."""
    pagina = _pagina()
    cuerpo_helper = _funcion("_dictamenLoEscribioLaIA", pagina)
    assert "indexOf" in cuerpo_helper and "=== -1" in cuerpo_helper, (
        "El helper no distingue: o marca todo como IA o nada. Un modelo real "
        "(groq, claude…) no está en la lista de caminos sin IA y por tanto SÍ "
        "es de la IA."
    )
    cuerpo = _funcion("renderAccionIA", pagina)
    assert "'La IA'" in cuerpo, "Ya nada dice «La IA» cuando el dictamen sí lo escribió la IA."
    assert "💡 La IA recomienda" in cuerpo, (
        "Se perdió el título original para el caso en que la IA sí corrió."
    )
